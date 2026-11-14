from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.routers.payments import financial_response_headers, payment_provider
from app.schemas.payment import Claim, ClaimResponse, IssueResolution, Resolution
from app.services.auth import get_current_user
from app.services.payments import PaymentService

router = APIRouter(dependencies=[Depends(financial_response_headers)])


@router.get("")
def dispute_queue(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models import BorrowRequest
    from app.payment_models import FinancialAudit, RefundIntent, RentalBooking, RentalDispute

    if not user.is_admin:
        raise HTTPException(403, "Administrator access required")
    return [
        {
            "booking_id": booking.id,
            "borrow_request_id": booking.borrow_request_id,
            "handover_status": request.handover_status,
            "borrower_id": booking.borrower_id,
            "lender_id": booking.lender_id,
            "dispute": PaymentService._dispute_view(dispute),
            "refund": PaymentService._refund_view(refund),
            "gateway_review": bool(db.scalar(select(FinancialAudit.id).where(
                FinancialAudit.booking_id == booking.id,
                FinancialAudit.action == "gateway_refund_review_required",
            ).limit(1))),
        }
        for dispute, booking, request, refund in db.execute(
            select(RentalDispute, RentalBooking, BorrowRequest, RefundIntent)
            .select_from(RentalBooking)
            .join(BorrowRequest, BorrowRequest.id == RentalBooking.borrow_request_id)
            .outerjoin(RentalDispute, RentalDispute.booking_id == RentalBooking.id)
            .outerjoin(RefundIntent, RefundIntent.booking_id == RentalBooking.id)
            .where(
                or_(
                    RentalDispute.status.in_(["raised", "needs_claim", "escalated"]),
                    (BorrowRequest.handover_status == "issue_reported")
                    & RentalBooking.settlement_kind.is_(None),
                    RefundIntent.status.in_(["created", "dispatching", "pending", "failed", "unknown"]),
                    RentalBooking.id.in_(select(FinancialAudit.booking_id).where(
                        FinancialAudit.action == "gateway_refund_review_required"
                    )),
                )
            )
        ).all()
    ]


@router.post("/handover-issue/resolve")
def resolve_issue(
    data: IssueResolution,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider=Depends(payment_provider),
):
    return PaymentService(db, provider).resolve_issue(
        str(data.booking_id), user.id, data.action, data.reason, admin=bool(user.is_admin)
    )


@router.post("/raise")
def raise_claim(
    data: Claim,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider=Depends(payment_provider),
):
    return PaymentService(db, provider).claim(
        str(data.booking_id),
        user.id,
        data.claimed_deduction_paise,
        data.reason.strip(),
        {name: getattr(data, name) for name in ("inspection_id", "cv_run_id", "assessment_id")},
    )


@router.post("/respond")
def respond(
    data: ClaimResponse,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider=Depends(payment_provider),
):
    return PaymentService(db, provider).respond(
        str(data.booking_id), user.id, data.accepted, data.notes, data.claim_version
    )


@router.post("/settle")
def settle(
    data: Resolution,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider=Depends(payment_provider),
):
    return PaymentService(db, provider).resolve(
        str(data.booking_id),
        user.id,
        data.approved_deduction_paise,
        admin=bool(user.is_admin),
        reason=data.reason,
        claim_version=data.claim_version,
    )
