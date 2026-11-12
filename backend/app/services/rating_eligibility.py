"""Eligibility for the existing borrower/lender rating fields."""

from sqlalchemy import select

from app.payment_models import RefundIntent, RentalBooking, RentalDispute


def rating_eligible(db, request, booking=None):
    booking = booking or db.scalar(
        select(RentalBooking).where(RentalBooking.borrow_request_id == request.id)
    )
    if booking is None:
        # Preserve existing completed legacy rentals; do not infer paid funding.
        return request.handover_status == "return_confirmed" and not request.disputed_at
    refund = db.scalar(select(RefundIntent).where(RefundIntent.booking_id == booking.id))
    dispute = db.scalar(select(RentalDispute).where(RentalDispute.booking_id == booking.id))
    return bool(
        request.returned_at
        and request.return_photos
        and booking.payment_status == "captured"
        and booking.booking_status == "completed"
        and booking.deposit_state == "settled"
        and refund
        and refund.status == "processed"
        and booking.refunded_paise + booking.deduction_paise == booking.security_deposit_paise
        and (not dispute or (dispute.resolved_at and dispute.status == "settled_arbitrated"))
    )
