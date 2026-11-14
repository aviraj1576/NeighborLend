"""Damage-check steps of the lend lifecycle: before photos, shareable link, link resolve."""
import secrets
from datetime import datetime, timedelta

from damage_check import Conflict, DamageCheckError, DamageCheckService, Forbidden, NotFound
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BorrowRequest, BorrowRequestStatus, HandoverStatus, User
from app.routers.borrow_requests import _get_handover_request, _record_handover_event
from app.services.auth import get_current_user
from app.services.damage_integration import get_damage_service
from app.services.notifications import create_notification

router = APIRouter()

LINK_TTL_DAYS = 60
CLOSED_STATES = (HandoverStatus.return_confirmed.value, HandoverStatus.dispute_resolved.value)


def _http(exc: DamageCheckError) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, Forbidden):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, Conflict):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.post("/borrow-requests/{request_id}/damage-check/start")
async def start_damage_check(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: DamageCheckService = Depends(get_damage_service),
):
    """Lender creates (or re-opens) the damage check for this lend."""
    req, lender_id = _get_handover_request(request_id, db, current_user, lock=True)
    if current_user.id != lender_id:
        raise HTTPException(status_code=403, detail="Only the lender can start the condition check")
    if req.handover_status not in (HandoverStatus.pending.value, HandoverStatus.photos_uploaded.value):
        raise HTTPException(status_code=409, detail="The condition check can only be started before handover")
    if req.damage_check_id:
        return {"check_id": req.damage_check_id}
    try:
        view = await service.create_check(
            current_user.id, req.id, lender_id, req.borrower_id,
            item_class=req.listing.category if req.listing else None,
        )
    except DamageCheckError as exc:
        raise _http(exc)
    req.damage_check_id = view.id
    db.commit()
    return {"check_id": view.id}


@router.post("/borrow-requests/{request_id}/damage-check/share")
async def share_damage_check(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: DamageCheckService = Depends(get_damage_service),
):
    """Lender confirms all 6 before photos are in; mints the shareable link for the borrower."""
    req, lender_id = _get_handover_request(request_id, db, current_user, lock=True)
    if current_user.id != lender_id:
        raise HTTPException(status_code=403, detail="Only the lender can share the condition check")
    if req.handover_status not in (HandoverStatus.pending.value, HandoverStatus.photos_uploaded.value):
        raise HTTPException(status_code=409, detail="The condition check can only be shared before handover")
    if not req.damage_check_id:
        raise HTTPException(status_code=409, detail="Start the condition check first")
    try:
        check = await service.get_check(current_user.id, req.damage_check_id)
    except DamageCheckError as exc:
        raise _http(exc)
    if check.missing_before:
        raise HTTPException(
            status_code=409,
            detail="Missing before photos: " + ", ".join(check.missing_before),
        )

    first_share = req.handover_status == HandoverStatus.pending.value
    req.damage_link_token = req.damage_link_token or secrets.token_urlsafe(32)
    req.damage_link_expires_at = datetime.utcnow() + timedelta(days=LINK_TTL_DAYS)
    req.handover_status = HandoverStatus.photos_uploaded.value
    req.updated_at = datetime.utcnow()
    link = f"/damage-check/{req.damage_link_token}"
    if first_share:
        _record_handover_event(
            db, req, current_user,
            f"{current_user.name} uploaded 6 condition photos for {req.title}. Damage-check link: {link}",
        )
        create_notification(
            db, req.borrower_id, "damage_check_link", "Condition photos ready",
            f"{current_user.name} documented {req.title}'s condition. Keep this link for the return.",
            link, req.id,
        )
    db.commit()
    return {
        "link": link,
        "token": req.damage_link_token,
        "expires_at": req.damage_link_expires_at,
        "check_id": req.damage_check_id,
    }


@router.get("/damage-links/{token}")
def resolve_damage_link(
    token: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Resolve a shareable link. Only the lend's lender and borrower may use it."""
    req = db.query(BorrowRequest).filter(BorrowRequest.damage_link_token == token).first()
    if req is None:
        raise HTTPException(status_code=404, detail="Unknown or revoked link")
    lender_id = req.listing.owner_id if req.listing else None
    if current_user.id not in (req.borrower_id, lender_id):
        raise HTTPException(status_code=403, detail="This link does not belong to one of your lends")
    if req.handover_status in CLOSED_STATES or req.status == BorrowRequestStatus.closed:
        raise HTTPException(status_code=410, detail="This lend is closed")
    if req.damage_link_expires_at and req.damage_link_expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="This link has expired")
    return {
        "borrow_request_id": req.id,
        "check_id": req.damage_check_id,
        "role": "lender" if current_user.id == lender_id else "borrower",
        "handover_status": req.handover_status,
        "return_due_at": req.return_due_at,
    }
