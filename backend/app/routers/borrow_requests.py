import math
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, BorrowRequest, BorrowRequestStatus, Listing, ListingStatus
from app.schemas.borrow_request import BorrowRequestCreateIn, BorrowRequestOut, BorrowRequestUpdateIn
from app.schemas.notification import DisputeCreateIn
from app.services.auth import get_current_user
from app.services.notifications import create_notification

router = APIRouter()

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def _format_request_out(req: BorrowRequest, distance_km: Optional[float] = None) -> dict:
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
        "returned_at": req.returned_at,
        "disputed_at": req.disputed_at,
        "distance_km": distance_km,
        "created_at": req.created_at
    }

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
    query = db.query(BorrowRequest).filter(BorrowRequest.status == BorrowRequestStatus.open)
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
    all_reqs = db.query(BorrowRequest).filter(
        BorrowRequest.borrower_id == current_user.id,
        BorrowRequest.status != BorrowRequestStatus.cancelled
    ).all()
    return [_format_request_out(r) for r in all_reqs]


@router.get("/{request_id}", response_model=BorrowRequestOut)
def get_borrow_request(request_id: str, db: Session = Depends(get_db)):
    req = db.query(BorrowRequest).filter(
        BorrowRequest.id == request_id,
        BorrowRequest.status != BorrowRequestStatus.cancelled,
    ).first()
    if req is None:
        raise HTTPException(status_code=404, detail="Borrow request not found")
    return _format_request_out(req)


def _get_rental_participants(request_id: str, db: Session, current_user: User):
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


@router.post("/{request_id}/dispute")
def report_dispute(
    request_id: str,
    data: DisputeCreateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req, other_user_id = _get_rental_participants(request_id, db, current_user)
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
    req.status = BorrowRequestStatus.cancelled
    db.commit()
    return {"status": "ok"}
