from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc

from app.database import get_db
from app.models import (
    User, Listing, ListingStatus, Conversation, Message,
    NegotiationOffer, OfferStatus, BorrowRequest, BorrowRequestStatus
)
from app.schemas.chat import (
    ConversationSummaryOut, ConversationDetailOut, ConversationCreateIn,
    MessageOut, MessageCreateIn, OfferOut, OfferCreateIn, OfferCounterIn,
    ParticipantOut
)
from app.services.auth import get_current_user
from app.services.notifications import create_notification
from app.services.negotiation import calculate_rental_duration_and_cost, check_listing_availability, snapshot_offer_terms

router = APIRouter()

def _format_participant(user: Optional[User]) -> ParticipantOut:
    if not user:
        return ParticipantOut(id="", name="Unknown", username="unknown", avatar_url=None, trust_score=50.0)
    return ParticipantOut(
        id=user.id,
        name=user.name,
        username=user.username,
        avatar_url=user.avatar_url,
        trust_score=user.trust_score if user.trust_score is not None else 50.0
    )

def _format_message(msg: Message) -> MessageOut:
    sender_name = msg.sender.name if msg.sender else None
    sender_username = msg.sender.username if msg.sender else None
    return MessageOut(
        id=msg.id,
        conversation_id=msg.conversation_id,
        sender_id=msg.sender_id,
        sender_name=sender_name,
        sender_username=sender_username,
        content=msg.content,
        is_system=msg.is_system or False,
        created_at=msg.created_at
    )

def _format_offer(offer: NegotiationOffer) -> OfferOut:
    sender_name = offer.sender.name if offer.sender else None
    sender_username = offer.sender.username if offer.sender else None
    return OfferOut(
        id=offer.id,
        conversation_id=offer.conversation_id,
        listing_id=offer.listing_id,
        sender_id=offer.sender_id,
        sender_name=sender_name,
        sender_username=sender_username,
        daily_price=offer.daily_price,
        start_date=offer.start_date,
        end_date=offer.end_date,
        total_cost=offer.total_cost,
        borrower_id=offer.borrower_id_snapshot,
        lender_id=offer.lender_id_snapshot,
        daily_rate_paise=offer.daily_rate_paise,
        rental_fee_paise=offer.rental_fee_paise,
        security_deposit_paise=offer.security_deposit_paise,
        total_amount_paise=offer.total_amount_paise,
        message=offer.message,
        status=offer.status,
        parent_offer_id=offer.parent_offer_id,
        borrow_request_id=offer.borrow_request_id,
        created_at=offer.created_at,
        updated_at=offer.updated_at
    )

def _get_active_offer(offers: List[NegotiationOffer]) -> Optional[NegotiationOffer]:
    # Pending offer has highest priority, otherwise most recent
    pending = [o for o in offers if o.status == OfferStatus.pending]
    if pending:
        return pending[-1]
    if offers:
        return offers[-1]
    return None


def _bind_listing(db: Session, conv: Conversation, listing_id: str):
    """Legacy general chats bind once; existing offers can never switch listing."""
    if conv.listing_id is not None:
        if conv.listing_id != listing_id:
            raise HTTPException(409, "This conversation concerns another listing; open the listing's chat")
        return
    old_listing_ids = {o.listing_id for o in conv.offers}
    if old_listing_ids and old_listing_ids != {listing_id}:
        raise HTTPException(409, "Historical conversation contains other listings; open the listing's chat")
    existing = db.query(Conversation).filter(
        Conversation.borrower_id == conv.borrower_id,
        Conversation.lender_id == conv.lender_id,
        Conversation.listing_id == listing_id,
        Conversation.id != conv.id,
    ).first()
    if existing:
        raise HTTPException(409, "A conversation for this listing already exists; open the listing's chat")
    conv.listing_id = listing_id

# ==================== CONVERSATIONS ====================

@router.get("/conversations", response_model=List[ConversationSummaryOut])
def list_conversations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """List conversations for current user with the other participant and latest activity."""
    conversations = (
        db.query(Conversation)
        .filter(or_(Conversation.borrower_id == current_user.id, Conversation.lender_id == current_user.id))
        .order_by(desc(Conversation.updated_at))
        .all()
    )

    results = []
    for conv in conversations:
        is_borrower = (conv.borrower_id == current_user.id)
        other_user = conv.lender if is_borrower else conv.borrower

        last_msg = None
        if conv.messages:
            last_msg = _format_message(conv.messages[-1])

        active_offer = None
        act = _get_active_offer(conv.offers)
        if act:
            active_offer = _format_offer(act)

        results.append(ConversationSummaryOut(
            id=conv.id,
            listing_id=conv.listing_id,
            listing=conv.listing,
            borrower=_format_participant(conv.borrower),
            lender=_format_participant(conv.lender),
            other_participant=_format_participant(other_user),
            is_borrower=is_borrower,
            last_message=last_msg,
            active_offer=active_offer,
            created_at=conv.created_at,
            updated_at=conv.updated_at
        ))
    return results

@router.post("/conversations", response_model=ConversationDetailOut)
def create_or_get_conversation(
    data: ConversationCreateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return exactly the borrower's listing thread, retaining legacy general chats."""
    lender = db.query(User).filter(User.id == data.lender_id).first()
    if not lender:
        raise HTTPException(status_code=404, detail="User not found")
    if lender.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot start a conversation with yourself.")

    listing = None
    if data.listing_id:
        listing = db.query(Listing).filter(Listing.id == data.listing_id).first()
        if not listing or listing.owner_id != lender.id:
            raise HTTPException(404, "Listing not found for this lender")

    # Serialize lookup/adoption/insertion for this borrower on SQLite and PostgreSQL.
    # The unique index also protects scoped threads from other writers.
    db.query(User).filter(User.id == current_user.id).update(
        {User.trust_score: User.trust_score}, synchronize_session=False)
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.borrower_id == current_user.id,
            Conversation.lender_id == lender.id,
            Conversation.listing_id == data.listing_id,
        )
        .order_by(Conversation.created_at, Conversation.id)
        .first()
    )

    if not conv and listing:
        # Reuse an unambiguous historical thread without moving messages/offers.
        legacy = db.query(Conversation).filter(
            Conversation.borrower_id == current_user.id,
            Conversation.lender_id == lender.id,
            Conversation.listing_id.is_(None),
        ).order_by(Conversation.created_at, Conversation.id).all()
        matching = [c for c in legacy if {o.listing_id for o in c.offers} == {listing.id}]
        empty = [c for c in legacy if not c.offers and listing.status == ListingStatus.published]
        if matching or empty:
            conv = (matching or empty)[0]
            _bind_listing(db, conv, listing.id)

    if not conv:
        if listing and listing.status != ListingStatus.published:
            raise HTTPException(409, "Listing is not available for a new conversation")
        conv = Conversation(
            borrower_id=current_user.id,
            lender_id=lender.id,
            listing_id=data.listing_id,
        )
        db.add(conv)
        db.flush()

        # Add initial system message
        sys_msg = Message(
            conversation_id=conv.id,
            sender_id=current_user.id,
            content=f"Conversation started with {lender.name}" + (f" about {listing.name}." if listing else "."),
            is_system=True
        )
        db.add(sys_msg)
        create_notification(
            db,
            lender.id,
            "borrowing_request",
            "New borrowing request",
            f"{current_user.name} started a conversation with you.",
            f"/messages/{conv.id}",
        )

    if data.initial_message and data.initial_message.strip():
        user_msg = Message(
            conversation_id=conv.id,
            sender_id=current_user.id,
            content=data.initial_message.strip(),
            is_system=False
        )
        db.add(user_msg)
        conv.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(conv)

    is_borrower = (conv.borrower_id == current_user.id)
    active_offer = _format_offer(_get_active_offer(conv.offers)) if _get_active_offer(conv.offers) else None

    return ConversationDetailOut(
        id=conv.id,
        listing_id=conv.listing_id,
        listing=conv.listing,
        borrower=_format_participant(conv.borrower),
        lender=_format_participant(conv.lender),
        is_borrower=is_borrower,
        messages=[_format_message(m) for m in conv.messages],
        offers=[_format_offer(o) for o in conv.offers],
        active_offer=active_offer,
        created_at=conv.created_at,
        updated_at=conv.updated_at
    )

@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get full conversation details including messages and offers."""
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if current_user.id not in (conv.borrower_id, conv.lender_id):
        raise HTTPException(status_code=403, detail="Not authorized to view this conversation")

    is_borrower = (conv.borrower_id == current_user.id)
    active_offer = _format_offer(_get_active_offer(conv.offers)) if _get_active_offer(conv.offers) else None

    return ConversationDetailOut(
        id=conv.id,
        listing_id=conv.listing_id,
        listing=conv.listing,
        borrower=_format_participant(conv.borrower),
        lender=_format_participant(conv.lender),
        is_borrower=is_borrower,
        messages=[_format_message(m) for m in conv.messages],
        offers=[_format_offer(o) for o in conv.offers],
        active_offer=active_offer,
        created_at=conv.created_at,
        updated_at=conv.updated_at
    )

# ==================== MESSAGES ====================

@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageOut])
def get_messages(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all messages in a conversation."""
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if current_user.id not in (conv.borrower_id, conv.lender_id):
        raise HTTPException(status_code=403, detail="Not authorized to access messages")

    return [_format_message(m) for m in conv.messages]

@router.post("/conversations/{conversation_id}/messages", response_model=MessageOut)
def send_message(
    conversation_id: str,
    data: MessageCreateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a message in a conversation."""
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if current_user.id not in (conv.borrower_id, conv.lender_id):
        raise HTTPException(status_code=403, detail="Not authorized to send messages in this conversation")

    clean_content = data.content.strip()
    if not clean_content:
        raise HTTPException(status_code=400, detail="Message content cannot be empty")

    new_msg = Message(
        conversation_id=conv.id,
        sender_id=current_user.id,
        content=clean_content,
        is_system=False
    )
    conv.updated_at = datetime.utcnow()
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)

    return _format_message(new_msg)

# ==================== OFFERS & NEGOTIATION ====================

@router.get("/conversations/{conversation_id}/offers", response_model=List[OfferOut])
def get_offers(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all negotiation offers for a conversation."""
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if current_user.id not in (conv.borrower_id, conv.lender_id):
        raise HTTPException(status_code=403, detail="Not authorized to view offers")

    return [_format_offer(o) for o in conv.offers]

@router.post("/conversations/{conversation_id}/offers", response_model=OfferOut)
def create_offer(
    conversation_id: str,
    data: OfferCreateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new negotiation offer."""
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if current_user.id not in (conv.borrower_id, conv.lender_id):
        raise HTTPException(status_code=403, detail="Not authorized to make offers in this conversation")

    listing = db.query(Listing).filter(
        Listing.id == data.listing_id,
        Listing.owner_id == conv.lender_id,
        Listing.status == ListingStatus.published,
    ).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Choose an available listing owned by this conversation's lender")

    db.query(User).filter(User.id == conv.borrower_id).update(
        {User.trust_score: User.trust_score}, synchronize_session=False)
    db.refresh(conv)
    _bind_listing(db, conv, listing.id)

    # Date and duration validation
    try:
        days, total_cost = calculate_rental_duration_and_cost(data.daily_price, data.start_date, data.end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Minimum price validation if listing owner configured one
    if listing.min_price_per_day is not None:
        if data.daily_price < listing.min_price_per_day:
            raise HTTPException(
                status_code=400,
                detail=f"Offer price ₹{data.daily_price} is below the lender's minimum price of ₹{listing.min_price_per_day}/day."
            )

    # Check listing availability
    is_avail, reason = check_listing_availability(db, listing.id, data.start_date, data.end_date)
    if not is_avail:
        raise HTTPException(status_code=400, detail=reason)

    # Cancel previous pending offers in this conversation to avoid conflicts
    for old_offer in conv.offers:
        if old_offer.status == OfferStatus.pending:
            old_offer.status = OfferStatus.cancelled

    offer = NegotiationOffer(
        conversation_id=conv.id,
        listing_id=listing.id,
        sender_id=current_user.id,
        daily_price=data.daily_price,
        start_date=data.start_date,
        end_date=data.end_date,
        total_cost=total_cost,
        message=data.message,
        status=OfferStatus.pending
    )
    try:
        snapshot_offer_terms(offer, listing, conv)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    db.add(offer)
    db.flush()

    # Add system notification message in chat
    date_range = f"{data.start_date.strftime('%b %d, %Y')} to {data.end_date.strftime('%b %d, %Y')}"
    sys_content = f"🏷️ {current_user.name} made an offer: ₹{data.daily_price}/day for {days} day(s) (Total: ₹{total_cost}). Dates: {date_range}."
    if data.message:
        sys_content += f" Note: \"{data.message}\""

    sys_msg = Message(
        conversation_id=conv.id,
        sender_id=current_user.id,
        content=sys_content,
        is_system=True
    )
    db.add(sys_msg)
    recipient_id = conv.lender_id if current_user.id == conv.borrower_id else conv.borrower_id
    create_notification(
        db,
        recipient_id,
        "borrowing_request",
        "New borrowing request offer",
        f"{current_user.name} sent a rental offer for {listing.name}.",
        f"/messages/{conv.id}",
    )

    conv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(offer)

    return _format_offer(offer)

@router.post("/offers/{offer_id}/accept", response_model=OfferOut)
def accept_offer(
    offer_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Accept a pending negotiation offer.
    Validates recipient authorization, verifies item availability,
    supersedes conflicting pending offers, and generates a BorrowRequest for fulfillment.
    """
    offer = db.query(NegotiationOffer).filter(NegotiationOffer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    conv = offer.conversation
    if not conv or current_user.id not in (conv.borrower_id, conv.lender_id):
        raise HTTPException(status_code=403, detail="Not authorized")

    if offer.sender_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot accept your own offer. It must be accepted by the other party.")

    if offer.status != OfferStatus.pending:
        raise HTTPException(status_code=400, detail=f"Offer cannot be accepted because it is already '{offer.status.value}'.")

    db.query(User).filter(User.id == conv.borrower_id).update(
        {User.trust_score: User.trust_score}, synchronize_session=False)
    db.refresh(conv)
    _bind_listing(db, conv, offer.listing_id)
    if not offer.listing or offer.listing.owner_id != conv.lender_id:
        raise HTTPException(409, "Offer listing does not belong to this lender")

    # Serialize acceptance per listing on SQLite and PostgreSQL before overlap checks.
    db.query(Listing).filter(Listing.id == offer.listing_id).update(
        {Listing.updated_at: Listing.updated_at}, synchronize_session=False)
    db.refresh(offer)
    if offer.status != OfferStatus.pending:
        raise HTTPException(status_code=409, detail="Offer was already accepted")
    if offer.total_amount_paise is None:
        raise HTTPException(409, "Historical offer lacks agreed deposit terms; submit a new offer")
    # Recheck item availability
    is_avail, reason = check_listing_availability(db, offer.listing_id, offer.start_date, offer.end_date, exclude_offer_id=offer.id)
    if not is_avail:
        raise HTTPException(status_code=409, detail=f"Cannot accept offer: {reason}")

    # Mark offer as accepted
    offer.status = OfferStatus.accepted
    offer.updated_at = datetime.utcnow()

    # Cancel any other pending offers in this conversation
    for other in conv.offers:
        if other.id != offer.id and other.status == OfferStatus.pending:
            other.status = OfferStatus.cancelled

    # Integrate with BorrowRequest workflow
    borrow_req = BorrowRequest(
        borrower_id=conv.borrower_id,
        listing_id=offer.listing_id,
        title=f"Rental: {offer.listing.name if offer.listing else 'Item'}",
        category=offer.listing.category if offer.listing else "Other",
        description=f"Negotiated and agreed via conversation. Agreed rate: ₹{offer.daily_price}/day.",
        max_price_per_day=offer.daily_price,
        needed_from=offer.start_date,
        needed_until=offer.end_date,
        total_cost=offer.total_cost,
        handover_status="pending",
        latitude=offer.listing.latitude if offer.listing else None,
        longitude=offer.listing.longitude if offer.listing else None,
        radius_km=offer.listing.lending_radius_km if offer.listing else 10.0,
        address_text=offer.listing.address_text if offer.listing else "",
        status=BorrowRequestStatus.open  # Open status preserves borrower/lender fulfillment workflow
    )
    db.add(borrow_req)
    db.flush()
    offer.borrow_request_id = borrow_req.id
    from app.config import get_settings
    from app.services.payments import snapshot_booking
    from app.services.razorpay_service import configured_provider, ProviderError
    try:
        provider = configured_provider(get_settings())
    except ProviderError as exc:
        raise HTTPException(503, exc.code) from None
    if provider.kind == "disabled":
        raise HTTPException(503, "Payments disabled; new booking acceptance is unavailable")
    snapshot_booking(db, borrow_req, offer, provider.kind, actor=current_user.id)

    # Post system message into conversation
    date_range = f"{offer.start_date.strftime('%b %d, %Y')} - {offer.end_date.strftime('%b %d, %Y')}"
    sys_msg = Message(
        conversation_id=conv.id,
        sender_id=current_user.id,
        content=f"🎉 Offer of ₹{offer.daily_price}/day (Total: ₹{offer.total_cost} for {date_range}) was ACCEPTED by {current_user.name}. A borrow booking request has been initiated.",
        is_system=True
    )
    db.add(sys_msg)
    create_notification(
        db,
        offer.sender_id,
        "approval",
        "Rental offer approved",
        f"{current_user.name} approved your offer for {offer.listing.name if offer.listing else 'an item'}.",
        f"/messages/{conv.id}",
        borrow_req.id,
    )

    conv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(offer)

    return _format_offer(offer)

@router.post("/offers/{offer_id}/counter", response_model=OfferOut)
def counter_offer(
    offer_id: str,
    data: OfferCounterIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Counter an existing pending offer. Stores counter-offer as a new record to preserve history."""
    parent_offer = db.query(NegotiationOffer).filter(NegotiationOffer.id == offer_id).first()
    if not parent_offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    conv = parent_offer.conversation
    if not conv or current_user.id not in (conv.borrower_id, conv.lender_id):
        raise HTTPException(status_code=403, detail="Not authorized")

    if data.listing_id != parent_offer.listing_id:
        raise HTTPException(status_code=400, detail="A counter-offer must keep the original listing")

    if parent_offer.sender_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot counter your own offer. You can make a new offer instead.")

    if parent_offer.status != OfferStatus.pending:
        raise HTTPException(status_code=400, detail=f"Cannot counter offer because it is already '{parent_offer.status.value}'.")

    db.query(User).filter(User.id == conv.borrower_id).update(
        {User.trust_score: User.trust_score}, synchronize_session=False)
    db.refresh(conv)
    _bind_listing(db, conv, parent_offer.listing_id)
    db.refresh(parent_offer)
    if parent_offer.status != OfferStatus.pending:
        raise HTTPException(409, "Offer is no longer pending")

    # Calculate duration and cost
    try:
        days, total_cost = calculate_rental_duration_and_cost(data.daily_price, data.start_date, data.end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Min price check
    listing = parent_offer.listing
    if listing and listing.min_price_per_day is not None:
        if data.daily_price < listing.min_price_per_day:
            raise HTTPException(
                status_code=400,
                detail=f"Counter-offer price ₹{data.daily_price} is below the lender's minimum price of ₹{listing.min_price_per_day}/day."
            )

    # Check availability
    is_avail, reason = check_listing_availability(db, parent_offer.listing_id, data.start_date, data.end_date)
    if not is_avail:
        raise HTTPException(status_code=400, detail=reason)

    # Mark parent offer as countered
    parent_offer.status = OfferStatus.countered
    parent_offer.updated_at = datetime.utcnow()

    # Create new counter offer
    new_offer = NegotiationOffer(
        conversation_id=conv.id,
        listing_id=parent_offer.listing_id,
        sender_id=current_user.id,
        daily_price=data.daily_price,
        start_date=data.start_date,
        end_date=data.end_date,
        total_cost=total_cost,
        message=data.message,
        status=OfferStatus.pending,
        parent_offer_id=parent_offer.id
    )
    try:
        snapshot_offer_terms(new_offer, listing, conv)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    db.add(new_offer)
    db.flush()

    # Post system message
    date_range = f"{data.start_date.strftime('%b %d, %Y')} to {data.end_date.strftime('%b %d, %Y')}"
    sys_content = f"🔄 {current_user.name} countered: ₹{data.daily_price}/day for {days} day(s) (Total: ₹{total_cost}). Dates: {date_range}."
    if data.message:
        sys_content += f" Note: \"{data.message}\""

    sys_msg = Message(
        conversation_id=conv.id,
        sender_id=current_user.id,
        content=sys_content,
        is_system=True
    )
    db.add(sys_msg)
    create_notification(
        db,
        parent_offer.sender_id,
        "borrowing_request",
        "New counter-offer",
        f"{current_user.name} sent a counter-offer for {parent_offer.listing.name if parent_offer.listing else 'an item'}.",
        f"/messages/{conv.id}",
    )

    conv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(new_offer)

    return _format_offer(new_offer)

@router.post("/offers/{offer_id}/reject", response_model=OfferOut)
def reject_offer(
    offer_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reject a pending offer."""
    offer = db.query(NegotiationOffer).filter(NegotiationOffer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    conv = offer.conversation
    if not conv or current_user.id not in (conv.borrower_id, conv.lender_id):
        raise HTTPException(status_code=403, detail="Not authorized")

    if offer.sender_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot reject your own offer. You can cancel it instead.")

    if offer.status != OfferStatus.pending:
        raise HTTPException(status_code=400, detail=f"Cannot reject offer because it is already '{offer.status.value}'.")

    offer.status = OfferStatus.rejected
    offer.updated_at = datetime.utcnow()

    sys_msg = Message(
        conversation_id=conv.id,
        sender_id=current_user.id,
        content=f"❌ {current_user.name} rejected the offer of ₹{offer.daily_price}/day.",
        is_system=True
    )
    db.add(sys_msg)
    create_notification(
        db,
        offer.sender_id,
        "rejection",
        "Rental offer rejected",
        f"{current_user.name} rejected your offer for {offer.listing.name if offer.listing else 'an item'}.",
        f"/messages/{conv.id}",
        offer.borrow_request_id,
    )

    conv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(offer)

    return _format_offer(offer)
