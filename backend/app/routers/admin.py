"""Admin-only endpoints. Every route depends on require_admin, which checks users.is_admin
on the server; the client-side admin link is only a convenience."""
import json
from datetime import datetime
from typing import Literal, Optional

from damage_check._compat import to_dict
from damage_check.schemas import PHASES, VIEWS
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    AdminAuditLog, BorrowRequest, BorrowRequestStatus, Conversation, Dispute, DisputeStatus,
    HandoverStatus, Message, SupportTicket, SupportTicketStatus, User,
)
from app.routers.borrow_requests import _record_handover_event
from app.routers.chat import _format_message
from app.routers.support import get_support_user
from app.services.auth import require_admin
from app.services.damage_integration import get_damage_service
from app.services.notifications import create_notification

router = APIRouter()


class ResolveIn(BaseModel):
    outcome: Literal["lender", "borrower", "partial"]
    note: Optional[str] = Field(default=None, max_length=2000)


def _audit(db: Session, admin_id: str, action: str, target_type: str, target_id: str, detail: dict) -> None:
    """Append an audit row. The caller commits."""
    db.add(AdminAuditLog(
        admin_id=admin_id, action=action, target_type=target_type,
        target_id=target_id, detail=json.dumps(detail, default=str),
    ))


def _storage():
    return get_damage_service().storage


def _name(db: Session, user_id: Optional[str]) -> Optional[str]:
    user = db.get(User, user_id) if user_id else None
    return user.name if user else None


def _summary(db: Session, dispute: Dispute) -> dict:
    lend = db.get(BorrowRequest, dispute.borrow_request_id)
    lender = lend.listing.owner if lend and lend.listing else None
    record = _storage().load_check(dispute.check_id) if dispute.check_id else None
    return {
        "id": dispute.id,
        "borrow_request_id": dispute.borrow_request_id,
        "title": lend.title if lend else None,
        "reason": dispute.reason,
        "status": dispute.status.value if dispute.status else None,
        "outcome": dispute.outcome,
        "created_at": dispute.created_at,
        "raised_by_name": _name(db, dispute.raised_by),
        "lender": {"id": lender.id, "name": lender.name} if lender else None,
        "borrower": {"id": lend.borrower_id, "name": _name(db, lend.borrower_id)} if lend else None,
        "check_id": dispute.check_id,
        "check_status": record.status if record else None,
        "report_overall": record.report.overall if record and record.report else None,
        "damage_link_token": lend.damage_link_token if lend else None,
    }


def _get_dispute_or_404(db: Session, dispute_id: str, lock: bool = False) -> Dispute:
    query = db.query(Dispute)
    if lock:
        query = query.with_for_update()
    dispute = query.filter(Dispute.id == dispute_id).first()
    if dispute is None:
        raise HTTPException(status_code=404, detail="Dispute not found")
    return dispute


@router.get("/disputes")
def list_disputes(
    status: str = Query("open", pattern="^(open|resolved|all)$"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Dispute)
    if status != "all":
        query = query.filter(Dispute.status == DisputeStatus(status))
    return [_summary(db, d) for d in query.order_by(Dispute.created_at.desc()).all()]


@router.get("/disputes/{dispute_id}")
def get_dispute(
    dispute_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    dispute = _get_dispute_or_404(db, dispute_id)
    lend = db.get(BorrowRequest, dispute.borrow_request_id)
    record = _storage().load_check(dispute.check_id) if dispute.check_id else None
    detail = _summary(db, dispute)
    detail.update({
        "resolution_note": dispute.resolution_note,
        "resolved_at": dispute.resolved_at,
        "resolved_by_name": _name(db, dispute.resolved_by),
        "lend": {
            "needed_from": lend.needed_from if lend else None,
            "needed_until": lend.needed_until if lend else None,
            "borrowing_started_at": lend.borrowing_started_at if lend else None,
            "return_due_at": lend.return_due_at if lend else None,
            "returned_at": lend.returned_at if lend else None,
            "handover_status": lend.handover_status if lend else None,
        },
        "report": to_dict(record.report) if record and record.report else None,
        "lender_decision": to_dict(record.decision) if record and record.decision else None,
        "before_views": _storage().list_photos(dispute.check_id, "before") if record else [],
        "after_views": _storage().list_photos(dispute.check_id, "after") if record else [],
        "photo_url_template": f"/api/admin/disputes/{dispute.id}/photos/{{phase}}/{{view}}",
    })
    return detail


@router.get("/disputes/{dispute_id}/photos/{phase}/{view}")
def get_dispute_photo(
    dispute_id: str,
    phase: str,
    view: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if phase not in PHASES or view not in VIEWS:
        raise HTTPException(status_code=400, detail="Unknown phase or view")
    dispute = _get_dispute_or_404(db, dispute_id)
    if not dispute.check_id:
        raise HTTPException(status_code=404, detail="This dispute has no photos")
    found = _storage().load_photo(dispute.check_id, phase, view)
    if found is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    data, mime = found
    return Response(content=data, media_type=mime, headers={"Cache-Control": "private, max-age=300"})


@router.post("/disputes/{dispute_id}/resolve")
def resolve_dispute(
    dispute_id: str,
    data: ResolveIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    note = (data.note or "").strip()
    if data.outcome == "partial" and not note:
        raise HTTPException(status_code=422, detail="A note is required for a partial outcome")
    dispute = _get_dispute_or_404(db, dispute_id, lock=True)
    if dispute.status == DisputeStatus.resolved:
        raise HTTPException(status_code=409, detail="This dispute is already resolved")
    lend = db.query(BorrowRequest).with_for_update().filter(
        BorrowRequest.id == dispute.borrow_request_id
    ).first()
    if lend is None or lend.handover_status != HandoverStatus.disputed.value:
        raise HTTPException(status_code=409, detail="The lend is not in a disputed state")
    lender_id = lend.listing.owner_id if lend.listing else None

    now = datetime.utcnow()
    dispute.status = DisputeStatus.resolved
    dispute.outcome = data.outcome
    dispute.resolution_note = note or None
    dispute.resolved_by = admin.id
    dispute.resolved_at = now
    lend.handover_status = HandoverStatus.dispute_resolved.value
    lend.status = BorrowRequestStatus.closed
    lend.updated_at = now

    suffix = f" Admin note: {note}" if note else ""
    if data.outcome == "lender":
        lender_msg = f"The dispute for {lend.title} was resolved in your favor.{suffix}"
        borrower_msg = f"The dispute for {lend.title} was resolved in the lender's favor.{suffix}"
    elif data.outcome == "borrower":
        lender_msg = f"The dispute for {lend.title} was resolved in the borrower's favor.{suffix}"
        borrower_msg = f"The dispute for {lend.title} was resolved in your favor.{suffix}"
    else:
        lender_msg = borrower_msg = f"The dispute for {lend.title} was resolved with a shared outcome.{suffix}"
    link = f"/borrow-requests/{lend.id}"
    if lender_id:
        create_notification(db, lender_id, "dispute_resolved", "Dispute resolved", lender_msg, link, lend.id)
    create_notification(db, lend.borrower_id, "dispute_resolved", "Dispute resolved", borrower_msg, link, lend.id)
    _record_handover_event(
        db, lend, admin,
        f"NeighborLend admin resolved the dispute for {lend.title} (outcome: {data.outcome}).{suffix}",
    )
    _audit(db, admin.id, "dispute_resolved", "dispute", dispute.id,
           {"outcome": data.outcome, "note": note, "borrow_request_id": lend.id})
    db.commit()
    return _summary(db, dispute)


@router.get("/audit-logs")
def list_audit_logs(
    limit: int = Query(100, ge=1, le=500),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = db.query(AdminAuditLog).order_by(AdminAuditLog.created_at.desc()).limit(limit).all()
    names = {u.id: u.name for u in db.query(User).filter(User.id.in_({r.admin_id for r in rows})).all()}
    return [
        {
            "id": r.id, "admin_id": r.admin_id, "admin_name": names.get(r.admin_id),
            "action": r.action, "target_type": r.target_type, "target_id": r.target_id,
            "detail": json.loads(r.detail) if r.detail else None, "created_at": r.created_at,
        }
        for r in rows
    ]


# ==================== SUPPORT ESCALATIONS ====================

class SupportReplyIn(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


def _ticket_summary(db: Session, ticket: SupportTicket) -> dict:
    last_user_msg = (
        db.query(Message)
        .filter(Message.conversation_id == ticket.conversation_id, Message.sender_id == ticket.user_id)
        .order_by(Message.created_at.desc())
        .first()
    )
    return {
        "id": ticket.id,
        "conversation_id": ticket.conversation_id,
        "user": {"id": ticket.user_id, "name": _name(db, ticket.user_id)},
        "context_step": ticket.context_step,
        "entity_type": ticket.entity_type,
        "entity_id": ticket.entity_id,
        "status": ticket.status.value if ticket.status else None,
        "escalated_at": ticket.escalated_at,
        "created_at": ticket.created_at,
        "last_user_message": (last_user_msg.content[:140] if last_user_msg else None),
    }


def _get_ticket_or_404(db: Session, ticket_id: str) -> SupportTicket:
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Support ticket not found")
    return ticket


@router.get("/support/escalations")
def list_escalations(
    status: str = Query("escalated", pattern="^(escalated|closed|all)$"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(SupportTicket)
    if status == "all":
        query = query.filter(SupportTicket.status != SupportTicketStatus.bot)
    else:
        query = query.filter(SupportTicket.status == SupportTicketStatus(status))
    return [_ticket_summary(db, t) for t in query.order_by(SupportTicket.escalated_at.desc()).all()]


@router.get("/support/escalations/{ticket_id}")
def get_escalation(
    ticket_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ticket = _get_ticket_or_404(db, ticket_id)
    conv = db.query(Conversation).filter(Conversation.id == ticket.conversation_id).first()
    detail = _ticket_summary(db, ticket)
    detail["messages"] = [_format_message(m).model_dump(mode="json") for m in (conv.messages if conv else [])]
    return detail


@router.post("/support/escalations/{ticket_id}/reply")
def reply_to_escalation(
    ticket_id: str,
    data: SupportReplyIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    content = data.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Reply cannot be empty")
    ticket = _get_ticket_or_404(db, ticket_id)
    if ticket.status != SupportTicketStatus.escalated:
        raise HTTPException(status_code=409, detail="Only escalated chats can be replied to")
    support = get_support_user(db)
    message = Message(
        conversation_id=ticket.conversation_id, sender_id=support.id, content=content,
        is_system=False, meta=json.dumps({"admin": True}),
    )
    db.add(message)
    conv = db.query(Conversation).filter(Conversation.id == ticket.conversation_id).first()
    if conv:
        conv.updated_at = datetime.utcnow()
    create_notification(
        db, ticket.user_id, "support_reply", "NeighborLend Support replied",
        content[:120], f"/messages/{ticket.conversation_id}",
    )
    _audit(db, admin.id, "support_reply", "support_ticket", ticket.id, {"length": len(content)})
    db.commit()
    db.refresh(message)
    return _format_message(message)


@router.post("/support/escalations/{ticket_id}/close")
def close_escalation(
    ticket_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ticket = _get_ticket_or_404(db, ticket_id)
    if ticket.status == SupportTicketStatus.closed:
        raise HTTPException(status_code=409, detail="This chat is already closed")
    ticket.status = SupportTicketStatus.closed
    _audit(db, admin.id, "support_closed", "support_ticket", ticket.id, {})
    db.commit()
    return _ticket_summary(db, ticket)
