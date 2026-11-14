"""Damage-check steps of the lend lifecycle: before photos, shareable link, link resolve."""
import secrets
from datetime import datetime, timedelta

from damage_check import Conflict, DamageCheckError, DamageCheckService, Forbidden, NotFound
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    BorrowRequest, BorrowRequestStatus, Dispute, DisputeStatus, HandoverStatus, User,
)
from app.routers.borrow_requests import (
    _format_request_out, _get_handover_request, _record_handover_event,
)
from app.schemas.borrow_request import BorrowRequestOut
from app.services.auth import get_current_user
from app.services.damage_integration import get_damage_service
from app.services.notifications import create_notification

router = APIRouter()

LINK_TTL_DAYS = 60
REVIEW_WINDOW_HOURS = 72
NON_RETURN_DISPUTE_AFTER_DAYS = 7
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


class DisputeIn(BaseModel):
    reason: str = Field(..., max_length=2000)


def _apply_review_timeout(db: Session, req: BorrowRequest) -> bool:
    """Auto-approve a return the lender left unreviewed for REVIEW_WINDOW_HOURS.

    Applied lazily whenever the lend is read or acted on (no cron job). Returns True
    if it fired. Commits when it fires.
    """
    if not (req.handover_status == HandoverStatus.return_photos_uploaded.value and req.returned_at):
        return False
    if datetime.utcnow() - req.returned_at <= timedelta(hours=REVIEW_WINDOW_HOURS):
        return False
    db.refresh(req, with_for_update=True)  # re-check under lock so two readers cannot both fire
    if req.handover_status != HandoverStatus.return_photos_uploaded.value:
        return False
    now = datetime.utcnow()
    req.handover_status = HandoverStatus.return_confirmed.value
    req.return_confirmed_at = now
    req.return_confirmed_by = None  # None = confirmed by the system, not a person
    req.status = BorrowRequestStatus.closed
    create_notification(
        db, req.borrower_id, "return_confirmed", "Return auto-approved",
        f"The lender did not review the return of {req.title} within "
        f"{REVIEW_WINDOW_HOURS} hours, so it was approved automatically.",
        f"/borrow-requests/{req.id}", req.id,
    )
    lender_id = req.listing.owner_id if req.listing else None
    if lender_id:
        create_notification(
            db, lender_id, "return_confirmed", "Return auto-approved",
            f"You did not review the return of {req.title} within "
            f"{REVIEW_WINDOW_HOURS} hours, so it was approved automatically.",
            f"/borrow-requests/{req.id}", req.id,
        )
    db.commit()
    return True


@router.post("/borrow-requests/{request_id}/return/submit", response_model=BorrowRequestOut)
async def submit_return(
    request_id: str,
    background: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: DamageCheckService = Depends(get_damage_service),
):
    """Borrower submits the 6 return photos. Allowed any time during the rental
    (early return needs no special flag) and starts the AI comparison."""
    req, lender_id = _get_handover_request(request_id, db, current_user, lock=True)
    if current_user.id != req.borrower_id:
        raise HTTPException(status_code=403, detail="Only the borrower can submit the return")
    if req.handover_status == HandoverStatus.return_photos_uploaded.value:
        raise HTTPException(status_code=409, detail="Return already submitted")
    if req.handover_status != HandoverStatus.lender_confirmed.value:
        raise HTTPException(status_code=409, detail="The rental is not active, so it cannot be returned yet")
    if not req.damage_check_id:
        raise HTTPException(status_code=409, detail="This lend has no damage check")
    try:
        check = await service.get_check(current_user.id, req.damage_check_id)
        if check.missing_after:
            raise HTTPException(
                status_code=409,
                detail="Missing return photos: " + ", ".join(check.missing_after),
            )
        _, should_run = await service.start_analysis(current_user.id, req.damage_check_id)
    except DamageCheckError as exc:
        raise _http(exc)
    if should_run:
        background.add_task(service.run_analysis, req.damage_check_id)

    now = datetime.utcnow()
    req.handover_status = HandoverStatus.return_photos_uploaded.value
    req.returned_at = now
    req.updated_at = now
    create_notification(
        db, lender_id, "return_submitted", "Return photos submitted",
        f"{current_user.name} submitted return photos for {req.title}. Please approve or dispute within "
        f"{REVIEW_WINDOW_HOURS} hours.",
        f"/borrow-requests/{req.id}", req.id,
    )
    _record_handover_event(
        db, req, current_user,
        f"{current_user.name} submitted 6 return photos for {req.title}. AI comparison is running.",
    )
    db.commit()
    db.refresh(req)
    return _format_request_out(req, include_private_handover=True)


@router.post("/borrow-requests/{request_id}/return/approve", response_model=BorrowRequestOut)
async def approve_return(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: DamageCheckService = Depends(get_damage_service),
):
    """Lender approves the return; the lend closes."""
    req, lender_id = _get_handover_request(request_id, db, current_user, lock=True)
    if current_user.id != lender_id:
        raise HTTPException(status_code=403, detail="Only the lender can approve the return")
    if _apply_review_timeout(db, req):
        db.refresh(req)
        return _format_request_out(req, include_private_handover=True)
    if req.handover_status != HandoverStatus.return_photos_uploaded.value:
        raise HTTPException(status_code=409, detail="There is no submitted return to approve")
    if req.damage_check_id:
        try:  # best effort: record the lender's decision on the AI warning
            await service.decide(current_user.id, req.damage_check_id, "dismissed", "Lender approved the return")
        except DamageCheckError:
            pass  # analysis not finished yet; the approval still stands
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
    _record_handover_event(
        db, req, current_user,
        f"{current_user.name} confirmed return of {req.title}. Rental completed.",
    )
    db.commit()
    db.refresh(req)
    return _format_request_out(req, include_private_handover=True)


@router.post("/borrow-requests/{request_id}/return/dispute", response_model=BorrowRequestOut)
def dispute_return(
    request_id: str,
    data: DisputeIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lender raises a dispute; admins are notified and decide."""
    req, lender_id = _get_handover_request(request_id, db, current_user, lock=True)
    if current_user.id != lender_id:
        raise HTTPException(status_code=403, detail="Only the lender can raise a dispute")
    if _apply_review_timeout(db, req):
        raise HTTPException(
            status_code=409,
            detail="The review window elapsed; the return was approved automatically",
        )
    open_dispute = db.query(Dispute).filter(
        Dispute.borrow_request_id == req.id, Dispute.status == DisputeStatus.open
    ).first()
    if open_dispute or req.handover_status == HandoverStatus.disputed.value:
        raise HTTPException(status_code=409, detail="A dispute is already open for this lend")

    overdue = bool(
        req.return_due_at
        and datetime.utcnow() > req.return_due_at + timedelta(days=NON_RETURN_DISPUTE_AFTER_DAYS)
    )
    can_dispute = req.handover_status == HandoverStatus.return_photos_uploaded.value or (
        req.handover_status == HandoverStatus.lender_confirmed.value and overdue
    )
    if not can_dispute:
        raise HTTPException(
            status_code=409,
            detail="A dispute can be raised once return photos are submitted, or "
                   f"{NON_RETURN_DISPUTE_AFTER_DAYS} days after the due date if the item was not returned",
        )
    reason = data.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Dispute reason cannot be blank")

    now = datetime.utcnow()
    db.add(Dispute(
        borrow_request_id=req.id, check_id=req.damage_check_id,
        raised_by=current_user.id, reason=reason,
    ))
    req.handover_status = HandoverStatus.disputed.value
    req.disputed_at = now
    req.dispute_description = reason
    req.updated_at = now
    create_notification(
        db, req.borrower_id, "dispute", "Return Dispute Raised",
        f"{current_user.name} raised a dispute about the return of {req.title}. "
        "NeighborLend admins will review both photo sets and decide.",
        f"/borrow-requests/{req.id}", req.id,
    )
    for (admin_id,) in db.query(User.id).filter(User.is_admin.is_(True)).all():
        create_notification(
            db, admin_id, "admin_dispute", "Dispute raised",
            f"A dispute was raised for {req.title} and needs a decision.",
            "/admin/disputes", req.id,
        )
    _record_handover_event(
        db, req, current_user,
        f"{current_user.name} raised a dispute for {req.title}: {reason}. An admin will review it.",
    )
    db.commit()
    db.refresh(req)
    return _format_request_out(req, include_private_handover=True)
