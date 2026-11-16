"""'Chat with us': support threads in the existing conversations/messages tables."""
import re
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Conversation, Message, SupportTicket, SupportTicketStatus, User
from app.routers.chat import _format_message
from app.services.auth import get_current_user, hash_password
from app.services.notifications import create_notification
from app.services.support_bot import bot_message_fields, greeting_node, resolve_node

router = APIRouter()

SUPPORT_USERNAME = "nl_support"
STEP_RE = re.compile(r"^[a-z0-9_]{1,60}$")
ENTITY_TYPES = {"borrow_request", "listing"}


class SupportChatIn(BaseModel):
    context_step: str = Field(..., max_length=60)
    entity_type: Optional[str] = Field(default=None, max_length=30)
    entity_id: Optional[str] = Field(default=None, max_length=64)


class SupportMessageIn(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


def get_support_user(db: Session) -> User:
    """The shared support identity. Created on the fly so fresh databases work without seeding."""
    user = db.query(User).filter(User.username == SUPPORT_USERNAME).first()
    if user is None:
        user = User(
            name="NeighborLend Support", username=SUPPORT_USERNAME,
            email="support@neighborlend.local",
            password_hash=hash_password(secrets.token_urlsafe(24)),  # nobody logs in as support
        )
        db.add(user)
        db.flush()
    return user


def notify_admins(db: Session, title: str, message: str, link: str) -> None:
    for (admin_id,) in db.query(User.id).filter(User.is_admin.is_(True)).all():
        create_notification(db, admin_id, "support_escalation", title, message, link)


@router.post("/chat")
def open_support_chat(
    data: SupportChatIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Open (or re-open) the user's support thread for a step and post the bot's first message."""
    if not STEP_RE.match(data.context_step):
        raise HTTPException(status_code=422, detail="Invalid context_step")
    if data.entity_type is not None and data.entity_type not in ENTITY_TYPES:
        raise HTTPException(status_code=422, detail="Invalid entity_type")
    support = get_support_user(db)
    if current_user.id == support.id:
        raise HTTPException(status_code=400, detail="The support account cannot open a support chat")

    conv = db.query(Conversation).filter(
        Conversation.borrower_id == current_user.id, Conversation.lender_id == support.id
    ).first()
    if conv is None:
        conv = Conversation(borrower_id=current_user.id, lender_id=support.id)
        db.add(conv)
        db.flush()

    # Re-clicking the same step's button reuses its open ticket instead of piling up new ones.
    ticket = db.query(SupportTicket).filter(
        SupportTicket.conversation_id == conv.id,
        SupportTicket.context_step == data.context_step,
        SupportTicket.entity_id == data.entity_id,
        SupportTicket.status != SupportTicketStatus.closed,
    ).first()
    if ticket is None:
        ticket = SupportTicket(
            conversation_id=conv.id, user_id=current_user.id, context_step=data.context_step,
            entity_type=data.entity_type, entity_id=data.entity_id,
        )
        db.add(ticket)
        db.flush()
        ref = f", ref: {data.entity_type} {data.entity_id}" if data.entity_id else ""
        db.add(Message(
            conversation_id=conv.id, sender_id=support.id, is_system=True,
            content=f"Support request, step: {data.context_step}{ref}",
        ))
        node_id, node = greeting_node(data.context_step)
        db.add(Message(conversation_id=conv.id, sender_id=support.id, is_system=False,
                       **bot_message_fields(node_id, node)))
        conv.updated_at = datetime.utcnow()
    db.commit()
    return {"conversation_id": conv.id, "ticket_id": ticket.id}


@router.post("/conversations/{conversation_id}/messages")
def send_support_message(
    conversation_id: str,
    data: SupportMessageIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Store the user's message, run the bot tree and store its reply (unless a human has the chat)."""
    support = get_support_user(db)
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.borrower_id != current_user.id or conv.lender_id != support.id:
        raise HTTPException(status_code=403, detail="Not your support conversation")
    content = data.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content cannot be empty")

    user_msg = Message(conversation_id=conv.id, sender_id=current_user.id, content=content, is_system=False)
    db.add(user_msg)
    conv.updated_at = datetime.utcnow()

    ticket = db.query(SupportTicket).filter(
        SupportTicket.conversation_id == conv.id
    ).order_by(SupportTicket.created_at.desc()).first()

    bot_msg = None
    if ticket is None or ticket.status != SupportTicketStatus.escalated:
        node_id, node = resolve_node(content)
        if node.get("escalate"):
            if ticket is None:  # thread opened from the normal messages list, not a step button
                ticket = SupportTicket(conversation_id=conv.id, user_id=current_user.id, context_step="direct")
                db.add(ticket)
            ticket.status = SupportTicketStatus.escalated
            ticket.escalated_at = datetime.utcnow()
            notify_admins(
                db, "Support escalation",
                f"{current_user.name} needs help at step {ticket.context_step}.",
                "/admin/support",
            )
        bot_msg = Message(conversation_id=conv.id, sender_id=support.id, is_system=False,
                          **bot_message_fields(node_id, node))
        db.add(bot_msg)
    db.commit()
    db.refresh(user_msg)
    if bot_msg is not None:
        db.refresh(bot_msg)
    return {
        "user_message": _format_message(user_msg),
        "bot_message": _format_message(bot_msg) if bot_msg is not None else None,
        "escalated": bool(ticket and ticket.status == SupportTicketStatus.escalated),
    }
