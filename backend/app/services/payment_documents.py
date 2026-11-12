"""Private, locally issued Test Mode receipts from verified financial records."""

from html import escape

from fastapi import HTTPException
from sqlalchemy import select

from app.models import Listing, User
from app.payment_models import FinancialAudit, PaymentTransaction, RefundIntent, RentalBooking
from app.services.payments import authorize


def payment_document(db, booking_id: str, actor: str, *, admin=False, refund=False):
    booking = db.get(RentalBooking, booking_id)
    if booking is None:
        raise HTTPException(404, "Booking not found")
    authorize(booking, actor, admin=admin)
    capture = db.scalar(
        select(PaymentTransaction).where(
            PaymentTransaction.booking_id == booking.id,
            PaymentTransaction.transaction_type == "payment",
            PaymentTransaction.status == "captured",
        )
    )
    if booking.payment_status != "captured" or capture is None:
        raise HTTPException(409, "A verified captured payment is required")
    if (
        capture.amount_paise != booking.total_amount_paise
        or capture.currency != booking.currency
        or capture.provider != booking.provider
    ):
        raise HTTPException(409, "Payment records require reconciliation")
    borrower, lender = db.get(User, booking.borrower_id), db.get(User, booking.lender_id)
    listing = db.get(Listing, booking.listing_id)
    number = ("NL-REF-" if refund else "NL-PAY-") + capture.id
    title = "Refund acknowledgment" if refund else "Rental payment receipt"
    captured = db.scalar(
        select(FinancialAudit)
        .where(FinancialAudit.booking_id == booking.id, FinancialAudit.action == "payment_captured")
        .order_by(FinancialAudit.created_at)
    )

    def money(value):
        return f"INR {value // 100:,}.{value % 100:02d}"

    fields = [
        ("Document number", number),
        ("Rental reference", booking.borrow_request_id),
        ("Booking reference", booking.id),
        ("Item", listing.name if listing else "Unavailable"),
        (
            "Rental period (UTC)",
            f"{booking.start_date.isoformat()} to {booking.end_date.isoformat()}",
        ),
        ("Borrower", borrower.name if borrower else booking.borrower_id),
        ("Lender", lender.name if lender else booking.lender_id),
        ("Rental fee", money(booking.rental_fee_paise)),
        ("Refundable security deposit", money(booking.security_deposit_paise)),
        ("Total captured", money(capture.amount_paise)),
        (
            "Capture recorded at (UTC)",
            (captured.created_at if captured else capture.created_at).isoformat(),
        ),
        ("Provider", booking.provider),
        ("Provider order reference", capture.razorpay_order_id),
        ("Provider payment reference", capture.razorpay_payment_id),
        ("Payment status", "captured"),
    ]
    if refund:
        intent = db.scalar(select(RefundIntent).where(RefundIntent.booking_id == booking.id))
        if intent is None or intent.status != "processed" or booking.deposit_state != "settled":
            raise HTTPException(409, "Refund must be confirmed processed before acknowledgment")
        transaction = db.scalar(
            select(PaymentTransaction).where(
                PaymentTransaction.booking_id == booking.id,
                PaymentTransaction.transaction_type == "deposit_refund",
                PaymentTransaction.status == "processed",
                PaymentTransaction.razorpay_refund_id == intent.provider_refund_id,
            )
        )
        if intent.amount_paise and (
            transaction is None or transaction.amount_paise != intent.amount_paise
        ):
            raise HTTPException(409, "Refund records require reconciliation")
        fields.extend(
            [
                ("Refund reference", intent.id),
                ("Provider refund reference", intent.provider_refund_id or "No refund due"),
                ("Refund amount", money(intent.amount_paise)),
                ("Approved compensation", money(intent.deduction_paise)),
                (
                    "Refund status",
                    "processed" if intent.amount_paise else "No refund due; allocation settled",
                ),
            ]
        )
        settled = db.scalar(
            select(FinancialAudit)
            .where(
                FinancialAudit.booking_id == booking.id,
                FinancialAudit.action == "settlement_confirmed",
            )
            .order_by(FinancialAudit.created_at)
        )
        if settled:
            fields.append(("Settlement confirmed at (UTC)", settled.created_at.isoformat()))
    rows = "".join(
        f"<tr><th>{escape(label)}</th><td>{escape(str(value or 'Unavailable'))}</td></tr>"
        for label, value in fields
    )
    html = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<title>{title}</title><style>body{{font:16px system-ui;margin:3rem;max-width:900px}}
table{{border-collapse:collapse;width:100%}}th,td{{padding:.6rem;text-align:left;border-bottom:1px solid #ccc;overflow-wrap:anywhere}}
@media print{{body{{margin:1cm}}}}</style><h1>NeighborLend — {title}</h1>
<p><strong>TEST MODE — NO REAL MONEY</strong></p><table>{rows}</table>
<p>Locally issued rental document. This is not a Razorpay-issued document or tax invoice.
Deposit accounting and lender allocations are simulated; no lender payout is recorded.</p></html>"""
    return html, number + ".html"
