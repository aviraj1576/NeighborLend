import hashlib
import json
import re
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User
from app.payment_models import (
    PaymentTransaction,
    ProcessedWebhook,
    RefundAttempt,
    RefundIntent,
    RentalBooking,
    RentalEvidence,
)
from app.schemas.payment import DemoPayment, PaymentInput, RefundAction, VerifyPayment
from app.services.auth import get_current_user
from app.services.payments import PaymentService, audit, authorize, locked
from app.services.razorpay_service import (
    WEBHOOK_MAX_BODY_BYTES,
    ProviderError,
    configured_provider,
)


def financial_response_headers(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(dependencies=[Depends(financial_response_headers)])


def webhook_receipt_payload(event):
    """Persist reconciliation metadata, never card/contact/banking/OTP fields.

    Authentication and replay/conflict checks still use the original body hash.
    Reconciliation uses authoritative provider GETs, not these projected values.
    """
    result = {"event": event["event"], "payload": {}}
    for resource, prefix in (("order", "order"), ("payment", "pay"), ("refund", "rfnd")):
        data = event["payload"].get(resource)
        entity = data.get("entity") if isinstance(data, dict) else None
        if not isinstance(entity, dict):
            continue
        safe = {}
        for name, expected in (("id", prefix), ("order_id", "order"), ("payment_id", "pay")):
            value = entity.get(name)
            if (
                isinstance(value, str)
                and len(value) <= 128
                and re.fullmatch(expected + r"_[A-Za-z0-9]+", value)
            ):
                safe[name] = value
        for name in ("amount", "amount_paid", "amount_due", "created_at"):
            if type(entity.get(name)) is int:
                safe[name] = entity[name]
        if entity.get("currency") == "INR":
            safe["currency"] = "INR"
        if isinstance(entity.get("status"), str) and entity["status"] in {
            "created",
            "attempted",
            "paid",
            "authorized",
            "captured",
            "failed",
            "pending",
            "processed",
        }:
            safe["status"] = entity["status"]
        if type(entity.get("captured")) is bool:
            safe["captured"] = entity["captured"]
        result["payload"][resource] = {"entity": safe}
    return result


@router.post("/bookings/{booking_id}/evidence")
def upload_evidence(
    booking_id: str,
    stage: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.rental_evidence import PREFIX, save_evidence

    data = file.file.read(8_000_001)
    actor, target = user.id, None
    try:
        with locked(db, booking_id) as booking:
            authorize(booking, actor)
            row, target = save_evidence(db, booking, actor, stage, data)
            db.flush()
            result = {"id": row.id, "url": PREFIX + row.id, "stage": stage, "sha256": row.sha256}
            audit(
                db,
                booking,
                actor,
                "evidence_uploaded",
                evidence_id=row.id,
                stage=stage,
                sha256=row.sha256,
            )
        return result
    except BaseException:
        if target is not None:
            target.unlink(missing_ok=True)
        raise


@router.get("/evidence/{evidence_id}")
def evidence_content(
    evidence_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    from app.services.rental_evidence import read_evidence

    row = db.get(RentalEvidence, evidence_id)
    if row is None:
        raise HTTPException(404, "Evidence not found")
    booking = db.get(RentalBooking, row.booking_id)
    authorize(booking, user.id, admin=bool(user.is_admin))
    return Response(
        read_evidence(row),
        media_type=row.media_type,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/requests/{request_id}/rental")
def private_rental(
    request_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    from app.models import BorrowRequest
    from app.routers.borrow_requests import _format_request_out

    req = db.get(BorrowRequest, request_id)
    if not req:
        raise HTTPException(404, "Rental not found")
    booking = db.scalar(select(RentalBooking).where(RentalBooking.borrow_request_id == request_id))
    if booking:
        authorize(booking, user.id, admin=bool(user.is_admin))
    elif (
        user.id not in {req.borrower_id, req.listing.owner_id if req.listing else None}
        and not user.is_admin
    ):
        raise HTTPException(403, "Not authorized for this rental")
    return _format_request_out(req, include_private_handover=True)


def payment_provider():
    try:
        return configured_provider(get_settings())
    except ProviderError as exc:
        raise HTTPException(503, exc.code) from None


@router.get("/by-request/{request_id}")
def by_request(
    request_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider=Depends(payment_provider),
):
    from app.models import BorrowRequest

    req = db.get(BorrowRequest, request_id)
    if req is None:
        raise HTTPException(404, "Rental not found")
    if (
        user.id not in (req.borrower_id, req.listing.owner_id if req.listing else None)
        and not user.is_admin
    ):
        raise HTTPException(403, "Not authorized")
    row = db.scalar(select(RentalBooking).where(RentalBooking.borrow_request_id == request_id))
    if row is None:
        return {
            "legacy": True,
            "handover_unlocked": False,
            "message": "Legacy rental has no verified payment snapshot; arrange a new agreed booking",
        }
    actor, bid, admin = user.id, row.id, bool(user.is_admin)
    return PaymentService(db, provider).get(bid, actor, admin=admin)


@router.get("/bookings/{booking_id}")
def status(
    booking_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider=Depends(payment_provider),
):
    response.headers["Cache-Control"] = "no-store"
    return PaymentService(db, provider).get(booking_id, user.id, admin=bool(user.is_admin))


@router.post("/create-order")
def create_order(
    data: PaymentInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider=Depends(payment_provider),
):
    return PaymentService(db, provider).order(str(data.booking_id), user.id)


@router.post("/verify")
def verify(
    data: VerifyPayment,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider=Depends(payment_provider),
):
    return PaymentService(db, provider).verify(
        str(data.booking_id), user.id, data.order_id, data.payment_id, data.signature
    )


@router.post("/mock-confirm")
def demo(
    data: DemoPayment,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider=Depends(payment_provider),
):
    return PaymentService(db, provider).demo_pay(
        str(data.booking_id), user.id, data.outcome, data.payment_id
    )


@router.post("/reconcile")
def reconcile(
    data: PaymentInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider=Depends(payment_provider),
):
    service = PaymentService(db, provider)
    bid, actor = str(data.booking_id), user.id
    service.get(bid, actor)
    if provider.kind == "disabled":
        return service.get(bid, actor)
    with locked(db, bid) as booking:
        authorize(booking, actor, borrower=True)
        service._mode(booking)
    row = db.scalar(
        select(PaymentTransaction).where(
            PaymentTransaction.booking_id == bid, PaymentTransaction.transaction_type == "order"
        )
    )
    if row is None or not row.razorpay_order_id:
        return service.order(bid, actor)  # Uncertain create is reconciled by its stored receipt.
    oid = row.razorpay_order_id
    db.rollback()
    if provider.kind == "mock":
        return service.get(bid, actor)
    try:
        payments = provider.order_payments(oid)
        captured = [p for p in payments if p.get("status") == "captured"]
        if len(captured) > 1:
            raise HTTPException(409, "Multiple captures require manual review")
        if captured:
            return service.verify(bid, actor, oid, captured[0]["id"], reconcile=True)
        return service.get(bid, actor)
    except ProviderError as exc:
        raise HTTPException(503, exc.code) from None


@router.post("/refund-deposit")
def refund(
    data: PaymentInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider=Depends(payment_provider),
):
    service = PaymentService(db, provider)
    actor, bid = user.id, str(data.booking_id)
    service.clean_return(bid, actor)
    return service.reconcile_refund(bid, actor)


@router.post("/refunds/execute")
def execute_refund(
    data: RefundAction,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider=Depends(payment_provider),
):
    if provider.kind == "razorpay_test" and not data.gateway_refund_approved:
        raise HTTPException(403, "Explicit gateway refund approval is required")
    service = PaymentService(db, provider)
    if data.retry_failed:
        return service.retry_failed_refund(str(data.booking_id), user.id, admin=bool(user.is_admin))
    return service.execute_refund(
        str(data.booking_id), user.id, data.demo_outcome, admin=bool(user.is_admin)
    )


@router.post("/refunds/reconcile")
def refund_retry(
    data: RefundAction,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider=Depends(payment_provider),
):
    service = PaymentService(db, provider)
    if data.retry_failed:
        raise HTTPException(403, "New refund attempts require the explicit /refunds/execute action")
    return service.reconcile_refund(
        str(data.booking_id), user.id, data.demo_outcome, admin=bool(user.is_admin)
    )


@router.post("/cancel")
def cancel(
    data: PaymentInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider=Depends(payment_provider),
):
    return PaymentService(db, provider).cancel(str(data.booking_id), user.id)


@router.post("/webhook")
async def webhook(
    request: Request, db: Session = Depends(get_db), provider=Depends(payment_provider)
):
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > WEBHOOK_MAX_BODY_BYTES:
            raise HTTPException(413, "Webhook too large")
        raw.extend(chunk)
    raw = bytes(raw)
    event_id = request.headers.get("x-razorpay-event-id", "")
    if (
        provider.kind != "razorpay_test"
        or not event_id
        or len(event_id) > 128
        or not provider.verify_webhook(raw, request.headers.get("x-razorpay-signature"))
    ):
        raise HTTPException(400, "Invalid webhook signature or identifier")
    try:
        event = json.loads(raw)
        kind = event["event"]
        if kind not in {
            "payment.captured",
            "payment.authorized",
            "payment.failed",
            "order.paid",
            "refund.created",
            "refund.processed",
            "refund.failed",
        }:
            raise ValueError("Unsupported webhook")
        if not isinstance(event["payload"], dict):
            raise ValueError("Invalid payload")
        if kind == "refund.created":
            # Creation is informational, never evidence that money was returned.
            entity = event["payload"]["refund"]["entity"]
            if not isinstance(entity, dict):
                raise ValueError("Invalid refund entity")
            provider.identifier(entity["id"], "rfnd")
    except (ValueError, TypeError, KeyError):
        raise HTTPException(422, "Invalid webhook structure") from None
    except ProviderError:
        raise HTTPException(422, "Invalid webhook structure") from None
    digest = hashlib.sha256(raw).hexdigest()
    previous = db.get(ProcessedWebhook, event_id)
    if previous and previous.payload_sha256 != digest:
        raise HTTPException(409, "Webhook identifier reused with another payload")
    if previous and previous.status == "processed":
        return {"received": True, "duplicate": True}
    if previous is None:
        db.add(
            ProcessedWebhook(
                event_id=event_id,
                event_type=kind,
                payload_sha256=digest,
                payload=json.dumps(webhook_receipt_payload(event)),
            )
        )
        try:
            db.commit()  # Durable receipt precedes external reconciliation.
        except IntegrityError:
            db.rollback()
            previous = db.get(ProcessedWebhook, event_id)
            if previous.payload_sha256 != digest:
                raise HTTPException(409, "Conflicting webhook identifier") from None
    if kind == "refund.created":
        receipt = db.get(ProcessedWebhook, event_id)
        receipt.status, receipt.processed_at = "processed", datetime.utcnow()
        db.commit()
        return {"received": True, "ignored": True}
    try:
        service = PaymentService(db, provider)
        if kind.startswith("refund."):
            entity = event["payload"]["refund"]["entity"]
            intent = db.scalar(
                select(RefundIntent).where(RefundIntent.provider_refund_id == entity["id"])
            )
            if intent is None:
                # A webhook can precede the POST response. Recover by authoritative
                # receipt, never by a client-supplied amount or webhook notes.
                db.rollback()
                confirmed = provider.fetch_refund(entity["id"])
                if confirmed.get("id") != entity["id"]:
                    raise HTTPException(409, "Refund identifier mismatch")
                old_attempt = db.scalar(
                    select(RefundAttempt).where(RefundAttempt.provider_refund_id == entity["id"])
                )
                if old_attempt:
                    intent = db.get(RefundIntent, old_attempt.refund_id)
                    if confirmed.get("status") != "failed":
                        raise HTTPException(409, "Superseded refund requires administrator review")
                    receipt = db.get(ProcessedWebhook, event_id)
                    receipt.status, receipt.processed_at = "processed", datetime.utcnow()
                    db.commit()
                    return {"received": True, "superseded": True}
                intent = db.scalar(
                    select(RefundIntent).where(
                        RefundIntent.idempotency_key == confirmed.get("receipt")
                    )
                )
                if intent is None:
                    raise HTTPException(503, "Refund receipt pending reconciliation")
            booking = db.get(RentalBooking, intent.booking_id)
            bid, actor = booking.id, booking.borrower_id
            service.reconcile_refund(bid, actor)
        else:
            if kind == "order.paid":
                oid = event["payload"]["order"]["entity"]["id"]
                db.rollback()
                captured = [
                    p for p in provider.order_payments(oid) if p.get("status") == "captured"
                ]
                if len(captured) != 1:
                    raise HTTPException(503, "Payment reconciliation pending")
                entity = captured[0]
            else:
                entity = event["payload"]["payment"]["entity"]
                oid = entity["order_id"]
            order = db.scalar(
                select(PaymentTransaction).where(
                    PaymentTransaction.razorpay_order_id == oid,
                    PaymentTransaction.transaction_type == "order",
                )
            )
            if order is None:
                raise HTTPException(409, "Webhook references unknown order")
            booking = db.get(RentalBooking, order.booking_id)
            bid, actor, pid = booking.id, booking.borrower_id, entity["id"]
            service.verify(bid, actor, oid, pid, reconcile=True)
    except (KeyError, TypeError, ValueError):
        db.rollback()
        raise HTTPException(422, "Invalid webhook entity") from None
    except ProviderError as exc:
        db.rollback()
        raise HTTPException(503, exc.code) from None
    receipt = db.get(ProcessedWebhook, event_id)
    receipt.status, receipt.processed_at = "processed", datetime.utcnow()
    db.commit()
    return {"received": True}
