import json
import math
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    BorrowRequest,
    BorrowRequestStatus,
    HandoverStatus,
    Listing,
    ListingStatus,
    Message,
    OfferStatus,
    User,
)
from app.schemas.borrow_request import (
    BorrowRequestCreateIn,
    BorrowRequestOut,
)
from app.schemas.notification import DisputeCreateIn, HandoverIssueCreateIn
from app.services.auth import get_current_user
from app.services.negotiation import calculate_rental_duration_and_cost
from app.services.notifications import create_notification


# New schemas for handover workflow
class HandoverPhotosIn(BaseModel):
    photo_urls: List[str] = Field(..., min_length=1, max_length=10)

class HandoverConfirmIn(BaseModel):
    photo_urls: List[str] = Field(default_factory=list, max_length=10)
    condition_note: Optional[str] = Field(default=None, max_length=2000)

class ReturnPhotosIn(BaseModel):
    photo_urls: List[str] = Field(..., min_length=1, max_length=10)

class ReturnConfirmIn(BaseModel):
    approved: bool = True
    condition_note: Optional[str] = Field(default=None, max_length=2000)

class RatingIn(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None

router = APIRouter()

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def _format_request_out(
    req: BorrowRequest,
    distance_km: Optional[float] = None,
    *,
    include_private_handover: bool = False,
) -> dict:
    # Parse JSON photo arrays safely
    def parse_photos(photo_field: Optional[str]) -> List[str]:
        if not photo_field:
            return []
        try:
            return json.loads(photo_field)
        except (json.JSONDecodeError, TypeError):
            return []

    return {
        "id": req.id,
        "borrower_id": req.borrower_id,
        "borrower_name": req.borrower.name if req.borrower else "Anonymous",
        "borrower_trust_score": req.borrower.trust_score if req.borrower else 50.0,
        "title": req.title,
        "category": req.category,
        "description": req.description,
        "max_price_per_day": req.max_price_per_day,
        "needed_from": req.needed_from,
        "needed_until": req.needed_until,
        "latitude": req.latitude,
        "longitude": req.longitude,
        "radius_km": req.radius_km,
        "address_text": req.address_text,
        "status": req.status,
        "listing_id": req.listing_id,
        "lender_id": req.listing.owner_id if req.listing else None,
        "lender_name": req.listing.owner.name if req.listing and req.listing.owner else None,
        "lender_username": req.listing.owner.username if req.listing and req.listing.owner else None,
        "returned_at": req.returned_at,
        "disputed_at": req.disputed_at,
        "handover_status": req.handover_status,
        "handover_marked_at": req.handover_marked_at,
        "handover_confirmed_at": req.handover_confirmed_at,
        "handover_confirmed_by": req.handover_confirmed_by,
        "handover_issue_description": req.handover_issue_description if include_private_handover else None,
        "handover_issue_reported_at": req.handover_issue_reported_at,
        "handover_photos": parse_photos(req.handover_photos) if include_private_handover else [],
        "handover_confirmed_photos": parse_photos(req.handover_confirmed_photos) if include_private_handover else [],
        "return_photos": parse_photos(req.return_photos) if include_private_handover else [],
        "handover_condition_note": req.handover_condition_note if include_private_handover else None,
        "return_condition_note": req.return_condition_note if include_private_handover else None,
        "return_confirmed_at": req.return_confirmed_at,
        "return_confirmed_by": req.return_confirmed_by,
        "borrowing_started_at": req.borrowing_started_at,
        "return_due_at": req.return_due_at,
        "lender_rating": req.lender_rating,
        "borrower_rating": req.borrower_rating,
        "lender_rating_comment": req.lender_rating_comment,
        "borrower_rating_comment": req.borrower_rating_comment,
        "lender_rated_at": req.lender_rated_at,
        "borrower_rated_at": req.borrower_rated_at,
        "conversation_id": _handover_conversation_id(req) if include_private_handover else None,
        "distance_km": distance_km,
        "created_at": req.created_at
    }


def _handover_conversation_id(req: BorrowRequest) -> Optional[str]:
    offer = next(
        (offer for offer in req.negotiation_offers if offer.status == OfferStatus.accepted),
        None,
    )
    return offer.conversation_id if offer else None


def _get_handover_request(request_id: str, db: Session, current_user: User, *, lock: bool = False):
    if lock:
        from app.payment_models import RentalBooking
        # Match financial-service lock order: booking before physical rental.
        db.query(RentalBooking).filter_by(borrow_request_id=request_id).update(
            {RentalBooking.booking_status: RentalBooking.booking_status}, synchronize_session=False)
    query = db.query(BorrowRequest)
    if lock:
        query = query.with_for_update()
    req = query.filter(BorrowRequest.id == request_id).first()
    if req is None:
        raise HTTPException(status_code=404, detail="Borrow request not found")
    lender_id = req.listing.owner_id if req.listing else None
    if current_user.id not in (req.borrower_id, lender_id):
        raise HTTPException(status_code=403, detail="Not authorized for this handover")
    if req.listing_id is None or lender_id is None:
        raise HTTPException(status_code=409, detail="This request is not a negotiated rental")
    if lock:
        from app.services.payments import require_funded
        if req.status == BorrowRequestStatus.cancelled:
            raise HTTPException(409, "Cancelled rental cannot proceed to handover")
        require_funded(db, req)
    return req, lender_id


def _record_handover_event(db: Session, req: BorrowRequest, actor: User, content: str) -> None:
    conversation_id = _handover_conversation_id(req)
    if conversation_id:
        db.add(Message(
            conversation_id=conversation_id,
            sender_id=actor.id,
            content=content,
            is_system=True,
        ))


@router.get("/{request_id}/handover", response_model=BorrowRequestOut)
def get_handover(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req, _ = _get_handover_request(request_id, db, current_user)
    return _format_request_out(req, include_private_handover=True)


@router.post("/{request_id}/handover/mark-given")
@router.post("/{request_id}/handover/confirm")
def deprecated_handover(request_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_handover_request(request_id, db, current_user, lock=True)
    raise HTTPException(410, "Use the photo-backed upload-photos, borrower-confirm and lender-confirm workflow")

# ==================== NEW HANDOVER WORKFLOW ENDPOINTS ====================

@router.post("/{request_id}/handover/upload-photos", response_model=BorrowRequestOut)
def upload_handover_photos(
    request_id: str,
    data: HandoverPhotosIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lender uploads photos of the item before handover."""
    req, lender_id = _get_handover_request(request_id, db, current_user, lock=True)
    if current_user.id != lender_id:
        raise HTTPException(status_code=403, detail="Only the lender can upload handover photos")
    if req.handover_status not in (HandoverStatus.pending.value, HandoverStatus.photos_uploaded.value):
        raise HTTPException(status_code=409, detail="Handover is not in a state to upload photos")

    from app.payment_models import RentalBooking
    from app.services.rental_evidence import validate_references
    booking = db.query(RentalBooking).filter_by(borrow_request_id=req.id).one()
    validate_references(db, booking, current_user.id, "handover", data.photo_urls)
    req.handover_photos = json.dumps(data.photo_urls)
    req.handover_status = HandoverStatus.photos_uploaded.value
    req.updated_at = datetime.utcnow()
    create_notification(
        db, req.borrower_id, "handover_photos_uploaded", "Lender Uploaded Handover Photos",
        f"{current_user.name} uploaded photos of {req.title} for your review before handover.",
        f"/borrow-requests/{req.id}", req.id,
    )
    _record_handover_event(db, req, current_user, f"{current_user.name} uploaded {len(data.photo_urls)} handover photo(s) for {req.title}.")
    db.commit()
    db.refresh(req)
    return _format_request_out(req, include_private_handover=True)


@router.post("/{request_id}/handover/borrower-confirm", response_model=BorrowRequestOut)
def borrower_confirm_handover(
    request_id: str,
    data: HandoverConfirmIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Borrower confirms receipt of item after seeing lender's photos."""
    req, lender_id = _get_handover_request(request_id, db, current_user, lock=True)
    if current_user.id != req.borrower_id:
        raise HTTPException(status_code=403, detail="Only the borrower can confirm receipt")
    if req.handover_status != HandoverStatus.photos_uploaded.value:
        raise HTTPException(status_code=409, detail="Lender must upload photos first")
    if req.needed_from is None or req.needed_until is None:
        raise HTTPException(status_code=409, detail="Agreed rental dates are missing")

    try:
        days, _ = calculate_rental_duration_and_cost(
            req.max_price_per_day or 0, req.needed_from, req.needed_until
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"Invalid agreed rental dates: {exc}") from exc
    now = datetime.utcnow()
    req.handover_confirmed_photos = json.dumps(data.photo_urls) if data.photo_urls else None
    req.handover_condition_note = data.condition_note
    req.handover_status = HandoverStatus.borrower_confirmed.value
    from app.payment_models import RentalBooking
    payment_booking = db.query(RentalBooking).filter_by(borrow_request_id=req.id).first()
    from app.services.rental_evidence import validate_references
    validate_references(db, payment_booking, current_user.id, "receipt", data.photo_urls)
    req.handover_confirmed_at = now
    req.handover_confirmed_by = current_user.id
    create_notification(
        db, lender_id, "handover_confirmed", "Borrower Confirmed Receipt",
        f"{current_user.name} acknowledged receipt of {req.title}. Lender confirmation is still required.",
        f"/borrow-requests/{req.id}", req.id,
    )
    _record_handover_event(db, req, current_user, f"{current_user.name} acknowledged receipt of {req.title}. Awaiting lender confirmation before rental activation.")
    db.commit()
    db.refresh(req)
    return _format_request_out(req, include_private_handover=True)


@router.post("/{request_id}/handover/lender-confirm", response_model=BorrowRequestOut)
def lender_confirm_handover(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lender confirms the handover is complete after borrower marked as received."""
    req, lender_id = _get_handover_request(request_id, db, current_user, lock=True)
    if current_user.id != lender_id:
        raise HTTPException(status_code=403, detail="Only the lender can confirm handover")
    if req.handover_status != HandoverStatus.borrower_confirmed.value:
        raise HTTPException(status_code=409, detail="Borrower must confirm receipt first")

    now = datetime.utcnow()
    req.handover_status = HandoverStatus.lender_confirmed.value
    from app.payment_models import RentalBooking
    booking = db.query(RentalBooking).filter_by(borrow_request_id=req.id).one()
    booking.booking_status = "active"
    req.borrowing_started_at = now
    req.return_due_at = now + timedelta(days=booking.duration_days)
    req.status = BorrowRequestStatus.fulfilled
    req.updated_at = now
    create_notification(
        db, req.borrower_id, "handover_lender_confirmed", "Handover Complete",
        f"{current_user.name} confirmed the handover of {req.title}.",
        f"/borrow-requests/{req.id}", req.id,
    )
    _record_handover_event(db, req, current_user, f"{current_user.name} confirmed handover complete for {req.title}.")
    db.commit()
    db.refresh(req)
    return _format_request_out(req, include_private_handover=True)


@router.post("/{request_id}/handover/report-issue", response_model=BorrowRequestOut)
def report_handover_issue(
    request_id: str,
    data: HandoverIssueCreateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req, lender_id = _get_handover_request(request_id, db, current_user, lock=True)
    if current_user.id != req.borrower_id:
        raise HTTPException(status_code=403, detail="Only the borrower can report a handover issue")
    if req.handover_status not in (HandoverStatus.photos_uploaded.value, HandoverStatus.borrower_confirmed.value):
        raise HTTPException(status_code=409, detail="The item must be in handover state first")
    description = data.description.strip()
    if not description:
        raise HTTPException(status_code=422, detail="Issue description cannot be blank")

    req.handover_status = HandoverStatus.issue_reported.value
    req.handover_issue_description = description
    req.handover_issue_reported_at = datetime.utcnow()
    create_notification(
        db, lender_id, "handover_issue_reported", "Borrower Reported a Handover Issue",
        f"{current_user.name} reported an issue with {req.title}. Open the request and conversation to resolve it.",
        f"/borrow-requests/{req.id}", req.id,
    )
    _record_handover_event(db, req, current_user, f"{current_user.name} reported a handover issue for {req.title}: {description}")
    db.commit()
    db.refresh(req)
    return _format_request_out(req, include_private_handover=True)


@router.post("/{request_id}/rate-lender", response_model=BorrowRequestOut)
def rate_lender(
    request_id: str,
    data: RatingIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Borrower rates the lender after rental completion."""
    req, lender_id = _get_rental_participants(request_id, db, current_user)
    if current_user.id != req.borrower_id:
        raise HTTPException(status_code=403, detail="Only the borrower can rate the lender")
    from app.services.rating_eligibility import rating_eligible
    if not rating_eligible(db, req):
        raise HTTPException(status_code=409, detail="Ratings require confirmed return and completed financial settlement")
    if req.lender_rating is not None:
        raise HTTPException(status_code=409, detail="Lender already rated for this rental")

    req.lender_rating = data.rating
    req.lender_rating_comment = data.comment
    req.lender_rated_at = datetime.utcnow()
    _update_rating_aggregate(db, lender_id, data.rating)
    create_notification(
        db, lender_id, "rating", "You Received a Rating",
        f"{current_user.name} rated you {data.rating}/5 stars for {req.title}.",
        f"/borrow-requests/{req.id}", req.id,
    )
    _record_handover_event(db, req, current_user, f"{current_user.name} rated lender {data.rating}/5 stars for {req.title}.")
    db.commit()
    db.refresh(req)
    return _format_request_out(req, include_private_handover=True)


@router.post("/{request_id}/rate-borrower", response_model=BorrowRequestOut)
def rate_borrower(
    request_id: str,
    data: RatingIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lender rates the borrower after rental completion."""
    req, lender_id = _get_rental_participants(request_id, db, current_user)
    if current_user.id != req.listing.owner_id:
        raise HTTPException(status_code=403, detail="Only the lender can rate the borrower")
    from app.services.rating_eligibility import rating_eligible
    if not rating_eligible(db, req):
        raise HTTPException(status_code=409, detail="Ratings require confirmed return and completed financial settlement")
    if req.borrower_rating is not None:
        raise HTTPException(status_code=409, detail="Borrower already rated for this rental")

    req.borrower_rating = data.rating
    req.borrower_rating_comment = data.comment
    req.borrower_rated_at = datetime.utcnow()
    _update_rating_aggregate(db, req.borrower_id, data.rating)
    create_notification(
        db, req.borrower_id, "rating", "You Received a Rating",
        f"{current_user.name} rated you {data.rating}/5 stars for {req.title}.",
        f"/borrow-requests/{req.id}", req.id,
    )
    _record_handover_event(db, req, current_user, f"{current_user.name} rated borrower {data.rating}/5 stars for {req.title}.")
    db.commit()
    db.refresh(req)
    return _format_request_out(req, include_private_handover=True)


@router.post("", response_model=BorrowRequestOut)
@router.post("/", response_model=BorrowRequestOut)
def create_borrow_request(data: BorrowRequestCreateIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    req = BorrowRequest(
        borrower_id=current_user.id,
        title=data.title,
        category=data.category,
        description=data.description,
        max_price_per_day=data.max_price_per_day,
        needed_from=data.needed_from,
        needed_until=data.needed_until,
        latitude=data.latitude,
        longitude=data.longitude,
        radius_km=data.radius_km,
        address_text=data.address_text,
        status=BorrowRequestStatus.open
    )
    db.add(req)
    db.flush()
    matching_owners = db.query(Listing.owner_id).filter(
        Listing.status == ListingStatus.published,
        Listing.category == req.category,
        Listing.owner_id != current_user.id,
    )
    if req.max_price_per_day is not None:
        matching_owners = matching_owners.filter(Listing.price_per_day <= req.max_price_per_day)
    for (owner_id,) in matching_owners.distinct().all():
        create_notification(
            db,
            owner_id,
            "borrowing_request",
            "A neighbor needs an item",
            f"{current_user.name} is looking for: {req.title}",
            f"/borrow-requests/{req.id}",
            req.id,
        )
    db.commit()
    db.refresh(req)
    return _format_request_out(req)

@router.get("", response_model=List[BorrowRequestOut])
@router.get("/", response_model=List[BorrowRequestOut])
def list_borrow_requests(
    category: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_km: float = 50.0,
    db: Session = Depends(get_db)
):
    from sqlalchemy.orm import joinedload
    query = db.query(BorrowRequest).options(
        joinedload(BorrowRequest.listing)
    ).filter(BorrowRequest.status == BorrowRequestStatus.open)
    if category:
        query = query.filter(BorrowRequest.category == category)
        
    all_reqs = query.order_by(BorrowRequest.created_at.desc()).all()
    if lat is not None and lon is not None:
        results = []
        for r in all_reqs:
            if r.latitude is not None and r.longitude is not None:
                dist = haversine(lat, lon, r.latitude, r.longitude)
                if dist <= radius_km:
                    results.append((dist, r))
        results.sort(key=lambda x: x[0])
        return [_format_request_out(r, dist) for dist, r in results]
    
    return [_format_request_out(r) for r in all_reqs]

@router.get("/my", response_model=List[BorrowRequestOut])
def list_my_requests(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from sqlalchemy.orm import joinedload
    all_reqs = db.query(BorrowRequest).options(
        joinedload(BorrowRequest.listing)
    ).filter(
        BorrowRequest.borrower_id == current_user.id,
        BorrowRequest.status != BorrowRequestStatus.cancelled
    ).all()
    return [_format_request_out(r) for r in all_reqs]


@router.get("/{request_id}", response_model=BorrowRequestOut)
def get_borrow_request(request_id: str, db: Session = Depends(get_db)):
    from sqlalchemy.orm import joinedload
    req = db.query(BorrowRequest).options(
        joinedload(BorrowRequest.listing)
    ).filter(
        BorrowRequest.id == request_id,
        BorrowRequest.status != BorrowRequestStatus.cancelled,
    ).first()
    if req is None:
        raise HTTPException(status_code=404, detail="Borrow request not found")
    return _format_request_out(req)


def _update_rating_aggregate(db: Session, user_id: str, rating: int):
    # Lock the rated account so ratings from different rentals cannot lose updates.
    from sqlalchemy import func, update
    count = func.coalesce(User.rating_count, 0)
    average = func.coalesce(User.avg_rating, 0.0)
    db.execute(update(User).where(User.id == user_id).values(
        avg_rating=(average * count + rating) / (count + 1), rating_count=count + 1
    ))


def _get_rental_participants(request_id: str, db: Session, current_user: User):
    from app.payment_models import RentalBooking
    db.query(RentalBooking).filter_by(borrow_request_id=request_id).update(
        {RentalBooking.booking_status: RentalBooking.booking_status}, synchronize_session=False)
    req = db.query(BorrowRequest).with_for_update().filter(
        BorrowRequest.id == request_id
    ).first()
    if req is None:
        raise HTTPException(status_code=404, detail="Borrow request not found")
    if req.listing_id is None or req.listing is None:
        raise HTTPException(status_code=400, detail="This request is not a confirmed rental")
    if current_user.id not in (req.borrower_id, req.listing.owner_id):
        raise HTTPException(status_code=403, detail="Not authorized for this rental")
    other_user_id = req.listing.owner_id if current_user.id == req.borrower_id else req.borrower_id
    return req, other_user_id


@router.post("/{request_id}/return")
def report_return(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req, other_user_id = _get_rental_participants(request_id, db, current_user)
    from app.payment_models import RentalBooking
    if db.query(RentalBooking).filter_by(borrow_request_id=req.id).first():
        raise HTTPException(410, "Managed rentals require return/upload-photos; this legacy route cannot change them")
    if req.handover_status not in (HandoverStatus.not_applicable.value, HandoverStatus.lender_confirmed.value):
        raise HTTPException(status_code=409, detail="The rental is not active until handover is confirmed")
    if req.returned_at is not None:
        raise HTTPException(status_code=409, detail="This rental has already been reported as returned")
    req.returned_at = datetime.utcnow()
    create_notification(
        db,
        other_user_id,
        "return",
        "Item return reported",
        f"{current_user.name} reported the return for {req.title}.",
        f"/borrow-requests/{req.id}",
        req.id,
    )
    db.commit()
    return {"status": "ok", "returned_at": req.returned_at}


@router.post("/{request_id}/return/upload-photos", response_model=BorrowRequestOut)
def upload_return_photos(
    request_id: str,
    data: ReturnPhotosIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Borrower uploads photos of item being returned."""
    req, lender_id = _get_rental_participants(request_id, db, current_user)
    if current_user.id != req.borrower_id:
        raise HTTPException(status_code=403, detail="Only the borrower can upload return photos")
    if req.handover_status not in (HandoverStatus.lender_confirmed.value, HandoverStatus.return_photos_uploaded.value):
        raise HTTPException(status_code=409, detail="Return photos can only be uploaded for active rentals")
    if req.returned_at is not None:
        raise HTTPException(status_code=409, detail="Return already reported")

    from app.payment_models import RentalBooking
    payment_booking = db.query(RentalBooking).filter_by(borrow_request_id=req.id).first()
    if payment_booking:
        from app.services.rental_evidence import validate_references
        if payment_booking.payment_status != "captured" or payment_booking.settlement_kind:
            raise HTTPException(409, "Return requires an unsettled funded booking")
        validate_references(db, payment_booking, current_user.id, "return", data.photo_urls)
    else:
        raise HTTPException(409, "Legacy rental evidence requires platform review")
    req.return_photos = json.dumps(data.photo_urls)
    req.handover_status = HandoverStatus.return_photos_uploaded.value
    if payment_booking and payment_booking.booking_status != "disputed":
        payment_booking.booking_status = "returned"
    req.returned_at = datetime.utcnow()
    req.updated_at = datetime.utcnow()
    create_notification(
        db, lender_id, "return_photos_uploaded", "Borrower Uploaded Return Photos",
        f"{current_user.name} uploaded photos for return of {req.title}. Please review and confirm.",
        f"/borrow-requests/{req.id}", req.id,
    )
    _record_handover_event(db, req, current_user, f"{current_user.name} uploaded {len(data.photo_urls)} return photo(s) for {req.title}.")
    db.commit()
    db.refresh(req)
    return _format_request_out(req, include_private_handover=True)


@router.post("/{request_id}/return/confirm", response_model=BorrowRequestOut)
def confirm_return(
    request_id: str,
    data: ReturnConfirmIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lender confirms return of item (or initiates dispute if not approved)."""
    req, lender_id = _get_rental_participants(request_id, db, current_user)
    if current_user.id != req.listing.owner_id:
        raise HTTPException(status_code=403, detail="Only the lender can confirm return")
    from app.payment_models import RentalBooking
    booking = db.query(RentalBooking).filter_by(borrow_request_id=req.id).first()
    if booking:
        from app.routers.payments import payment_provider
        from app.services.payments import PaymentService
        actor, bid, rid = current_user.id, booking.id, req.id
        provider = payment_provider()
        service = PaymentService(db, provider)
        service.return_decision(bid, actor, data.approved, data.condition_note or "")
        req = db.get(BorrowRequest, rid)
        db.refresh(req)
        return _format_request_out(req, include_private_handover=True)
    if req.handover_status != HandoverStatus.return_photos_uploaded.value:
        raise HTTPException(status_code=409, detail="Return photos must be uploaded by borrower first")
    if req.returned_at is None:
        raise HTTPException(status_code=409, detail="Return not yet reported")

    if data.approved:
        now = datetime.utcnow()
        req.handover_status = HandoverStatus.return_confirmed.value
        req.return_confirmed_at = now
        req.return_confirmed_by = current_user.id
        req.status = BorrowRequestStatus.closed
        create_notification(
            db, req.borrower_id, "return_confirmed", "Return Confirmed",
            f"{current_user.name} confirmed return of {req.title}. Rental completed successfully.",
            f"/borrow-requests/{req.id}", req.id,
        )
        _record_handover_event(db, req, current_user, f"{current_user.name} confirmed return of {req.title}. Rental completed.")
        db.commit()
        db.refresh(req)
        return _format_request_out(req, include_private_handover=True)
    else:
        # Dispute initiated
        req.disputed_at = datetime.utcnow()
        req.dispute_description = data.condition_note or "Lender did not approve return condition"
        create_notification(
            db, req.borrower_id, "dispute", "Return Dispute Initiated",
            f"{current_user.name} raised a dispute for return of {req.title}.",
            f"/borrow-requests/{req.id}", req.id,
        )
        _record_handover_event(db, req, current_user, f"{current_user.name} initiated a dispute for return of {req.title}: {req.dispute_description}")
        db.commit()
        db.refresh(req)
        return _format_request_out(req, include_private_handover=True)


@router.post("/{request_id}/dispute")
def report_dispute(
    request_id: str,
    data: DisputeCreateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req, other_user_id = _get_rental_participants(request_id, db, current_user)
    from app.payment_models import RentalBooking
    booking = db.query(RentalBooking).filter_by(borrow_request_id=req.id).first()
    if booking:
        from app.routers.payments import payment_provider
        from app.services.payments import PaymentService
        if not data.description.strip():
            raise HTTPException(422, "Dispute reason required")
        result = PaymentService(db, payment_provider()).escalate(booking.id, current_user.id, data.description.strip())
        return {"status": "ok", "dispute": result}
    if req.handover_status not in (HandoverStatus.not_applicable.value, HandoverStatus.lender_confirmed.value):
        raise HTTPException(status_code=409, detail="The rental is not active until handover is confirmed")
    if req.disputed_at is not None:
        raise HTTPException(status_code=409, detail="A dispute has already been reported for this rental")
    description = data.description.strip()
    if not description:
        raise HTTPException(status_code=422, detail="Dispute description cannot be blank")
    req.disputed_at = datetime.utcnow()
    req.dispute_description = description
    create_notification(
        db,
        other_user_id,
        "dispute",
        "A rental dispute was reported",
        f"{current_user.name} reported a dispute for {req.title}.",
        f"/borrow-requests/{req.id}",
        req.id,
    )
    db.commit()
    return {"status": "ok", "disputed_at": req.disputed_at}

@router.delete("/{request_id}")
def delete_borrow_request(request_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    req = db.query(BorrowRequest).filter(BorrowRequest.id == request_id, BorrowRequest.borrower_id == current_user.id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Borrow request not found")
    from app.payment_models import RentalBooking
    booking = db.query(RentalBooking).filter_by(borrow_request_id=req.id).first()
    if booking:
        from app.routers.payments import payment_provider
        from app.services.payments import PaymentService
        PaymentService(db, payment_provider()).cancel(booking.id, current_user.id)
        return {"status": "ok"}
    if req.status == BorrowRequestStatus.fulfilled:
        raise HTTPException(409, "An active legacy rental requires manual return review")
    req.status = BorrowRequestStatus.cancelled
    db.commit()
    return {"status": "ok"}
