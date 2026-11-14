"""Read-only gateway evidence, separate from settlement authority and the ledger."""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.payment_models import PaymentTransaction, RefundAttempt, RefundIntent, RentalBooking
from app.services.razorpay_service import ProviderError


def inspect_refunds(db, provider, booking_id, actor, *, admin=False):
    from app.services.payments import authorize

    booking = db.get(RentalBooking, booking_id)
    if booking is None:
        raise HTTPException(404, "Booking not found")
    authorize(booking, actor, admin=admin)
    if provider.kind != "razorpay_test" or booking.provider != provider.kind:
        raise HTTPException(409, "Gateway inspection requires the booking's Razorpay Test provider")
    payment = db.scalar(
        select(PaymentTransaction).where(
            PaymentTransaction.booking_id == booking.id,
            PaymentTransaction.transaction_type == "payment",
            PaymentTransaction.status == "captured",
        )
    )
    if payment is None:
        raise HTTPException(409, "A captured payment is required for gateway inspection")
    intent = db.scalar(select(RefundIntent).where(RefundIntent.booking_id == booking.id))
    known = set()
    keys = set()
    if intent:
        known.update(
            v
            for v in db.scalars(
                select(RefundAttempt.provider_refund_id).where(RefundAttempt.refund_id == intent.id)
            )
            if v
        )
        if intent.provider_refund_id:
            known.add(intent.provider_refund_id)
        keys.add(intent.idempotency_key)
    target = dict(
        booking_id=booking.id,
        payment_id=payment.razorpay_payment_id,
        order_id=payment.razorpay_order_id,
        amount=booking.total_amount_paise,
        authorized=intent.amount_paise if intent else 0,
        processed=intent.amount_paise if intent and intent.status == "processed" else 0,
    )
    # No connection/row lock is held over provider network operations.
    db.rollback()
    result = {
        "status": "unavailable",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "booking_id": target["booking_id"],
        "authorized_refund_paise": target["authorized"],
        "refunds": [],
        "external_refunds": [],
        "issues": [],
    }
    try:
        remote, refunds = provider.refund_snapshot(target["payment_id"])
        if (
            not isinstance(remote, dict)
            or not isinstance(refunds, list)
            or any(not isinstance(r, dict) for r in refunds)
        ):
            raise ProviderError("invalid_provider_response")
        if (
            remote.get("id") != target["payment_id"]
            or remote.get("order_id") != target["order_id"]
            or type(remote.get("amount")) is not int
            or remote["amount"] != target["amount"]
            or remote.get("currency") != "INR"
            or remote.get("livemode") is True
            or not isinstance(remote.get("status"), str)
            or remote["status"] not in {"captured", "refunded"}
            or remote.get("captured") is False
            or type(remote.get("amount_refunded")) is not int
            or not 0 <= remote["amount_refunded"] <= target["amount"]
        ):
            raise ProviderError("gateway_payment_mismatch")
        seen, processed, pending, active = set(), 0, 0, 0
        for refund in refunds:
            identity = provider.identifier(refund.get("id"), "rfnd")
            if (
                identity in seen
                or refund.get("payment_id") != target["payment_id"]
                or type(refund.get("amount")) is not int
                or refund["amount"] <= 0
                or refund.get("currency") != "INR"
                or refund.get("livemode") is True
                or not isinstance(refund.get("status"), str)
                or refund["status"] not in {"processed", "pending", "failed"}
            ):
                raise ProviderError("gateway_refund_mismatch")
            seen.add(identity)
            current = (
                isinstance(refund.get("receipt"), str)
                and refund["receipt"] in keys
                and refund["amount"] == target["authorized"]
            )
            expected = identity in known or current
            item = {
                "id": identity,
                "amount_paise": refund["amount"],
                "status": refund["status"],
                "authorized": expected,
                "current_intent": current,
            }
            result["refunds"].append(item)
            if not expected:
                result["external_refunds"].append(item)
            if refund["status"] != "failed":
                active += refund["amount"]
            if refund["status"] == "processed":
                processed += refund["amount"]
            if refund["status"] == "pending":
                pending += refund["amount"]
            if expected and refund["amount"] != target["authorized"]:
                result["issues"].append("authorized_refund_amount_mismatch")
        if result["external_refunds"]:
            result["issues"].append("unmatched_gateway_refund")
        if active > target["authorized"]:
            result["issues"].append("refund_exceeds_authorized_allocation")
        if not processed <= remote["amount_refunded"] <= active:
            result["issues"].append("gateway_refund_totals_inconsistent")
        if (
            target["processed"]
            and sum(
                r["amount_paise"]
                for r in result["refunds"]
                if r["authorized"] and r["status"] == "processed"
            )
            != target["processed"]
        ):
            result["issues"].append("saved_refund_not_confirmed")
        result.update(
            status="review_required" if result["issues"] else "verified",
            issues=sorted(set(result["issues"])),
            amount_refunded_paise=remote["amount_refunded"],
            processed_refunds_paise=processed,
            pending_refunds_paise=pending,
            remaining_gross_paise=target["amount"] - active,
            payment_status=remote["status"],
        )
    except ProviderError as exc:
        result.update(status="unavailable", error_code=exc.code)
    return result
