"""Application-authorized test payments. Network calls never hold a DB transaction."""

import json
import re
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models import BorrowRequest, BorrowRequestStatus, NegotiationOffer, OfferStatus
from app.payment_models import (
    EscrowLedgerEntry,
    FinancialAudit,
    JournalTransaction,
    PaymentTransaction,
    RefundAttempt,
    RefundIntent,
    RentalBooking,
    RentalDispute,
)
from app.services.escrow_service import paise, post
from app.services.razorpay_service import MAX_AMOUNT_PAISE, ProviderError


def conflict(message):
    raise HTTPException(409, message)


def audit(db, booking, actor, action, **details):
    db.add(
        FinancialAudit(
            booking_id=booking.id,
            actor_id=actor,
            action=action,
            details=json.dumps(details, sort_keys=True),
        )
    )
    # In-app delivery is committed with the financial event; it cannot announce a rollback.
    from app.models import User
    from app.services.notifications import create_notification

    recipients = {booking.borrower_id, booking.lender_id}
    if action in {"dispute_escalated", "refund_unknown", "refund_failed"}:
        recipients.update(db.scalars(select(User.id).where(User.is_admin.is_(True))).all())
    for recipient in recipients - {actor}:
        create_notification(
            db,
            recipient,
            "test_payment",
            "Test payment update",
            action.replace("_", " ").capitalize(),
            f"/borrow-requests/{booking.borrow_request_id}",
            booking.borrow_request_id,
        )


@contextmanager
def locked(db, booking_id):
    # Authentication reads may have autobegun a transaction. No mutations precede this boundary.
    db.rollback()
    try:
        if db.bind.dialect.name == "sqlite":
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        booking = db.scalar(
            select(RentalBooking).where(RentalBooking.id == booking_id).with_for_update()
        )
        if booking is None:
            raise HTTPException(404, "Booking not found")
        yield booking
        db.commit()
    except BaseException:
        db.rollback()
        raise


def authorize(booking, actor, *, borrower=False, lender=False, admin=False):
    allowed = (
        [booking.borrower_id]
        if borrower
        else [booking.lender_id]
        if lender
        else [booking.borrower_id, booking.lender_id]
    )
    if actor not in allowed and not admin:
        raise HTTPException(403, "Not authorized for this booking")


def snapshot_booking(db, request, offer, provider, actor=None):
    if provider not in {"mock", "razorpay_test"}:
        conflict("A sandbox payment provider is required")
    if request.listing_id != offer.listing_id:
        conflict("Accepted offer belongs to another listing")
    existing = db.scalar(select(RentalBooking).where(RentalBooking.borrow_request_id == request.id))
    if existing:
        if existing.offer_id != offer.id:
            conflict("Rental already belongs to another accepted offer")
        return existing
    if offer.status != OfferStatus.accepted or not offer.listing:
        conflict("An accepted offer and listing are required")
    days = max(1, (offer.end_date.date() - offer.start_date.date()).days)
    if offer.end_date < offer.start_date:
        conflict("Invalid agreed rental dates")
    try:
        daily, deposit = offer.daily_rate_paise, offer.security_deposit_paise
        if daily is None or deposit is None:
            conflict("Agreed deposit snapshot missing; submit a new offer")
    except ValueError as exc:
        raise HTTPException(422, "Invalid agreed price") from exc
    if (
        type(daily) is not int
        or type(deposit) is not int
        or deposit < 0
        or daily <= 0
        or days > 3650
        or daily * days + deposit > MAX_AMOUNT_PAISE
    ):
        conflict("Booking amount or duration outside supported limits")
    if paise(offer.total_cost) != daily * days:
        conflict("Agreed fee is inconsistent at paise precision; renegotiate the daily rate")
    if (
        offer.borrower_id_snapshot != request.borrower_id
        or offer.lender_id_snapshot != offer.listing.owner_id
        or offer.rental_fee_paise != daily * days
        or offer.total_amount_paise != daily * days + deposit
    ):
        conflict("Offer financial snapshot is inconsistent")
    booking = RentalBooking(
        borrow_request_id=request.id,
        offer_id=offer.id,
        listing_id=offer.listing_id,
        borrower_id=request.borrower_id,
        lender_id=offer.listing.owner_id,
        start_date=offer.start_date,
        end_date=offer.end_date,
        duration_days=days,
        daily_rate_paise=daily,
        rental_fee_paise=daily * days,
        security_deposit_paise=deposit,
        total_amount_paise=daily * days + deposit,
        provider=provider,
    )
    # Persist the accepted offer's request association before PostgreSQL checks
    # the snapshot at INSERT time; the application's autoflush can be disabled.
    db.flush()
    db.add(booking)
    db.flush()
    audit(db, booking, actor or request.borrower_id, "booking_snapshot_created")
    return booking


def require_funded(db, request):
    # Guard is shared by every old/new handover mutation. A legacy record is never funded by default.
    db.query(RentalBooking).filter(RentalBooking.borrow_request_id == request.id).update(
        {RentalBooking.booking_status: RentalBooking.booking_status}, synchronize_session=False
    )
    booking = db.scalar(
        select(RentalBooking)
        .where(RentalBooking.borrow_request_id == request.id)
        .execution_options(populate_existing=True)
    )
    if (
        booking is None
        or booking.payment_status != "captured"
        or booking.booking_status not in {"funded", "active"}
    ):
        conflict(
            "Verified payment is required before handover; legacy rentals require explicit review"
        )
    return booking


class PaymentService:
    def __init__(self, db, provider):
        self.db, self.provider = db, provider

    def _refund_admin(self, actor, admin):
        from app.models import User

        operator = self.db.get(User, actor)
        if not admin or operator is None or not operator.is_admin:
            raise HTTPException(403, "Only an administrator may operate refunds")

    def _mode(self, booking):
        try:
            if getattr(self.provider, "sandbox_only", False) is not True:
                raise ProviderError("sandbox_confirmation_required")
        except ProviderError as exc:
            raise HTTPException(503, exc.code) from None
        if self.provider.kind == "disabled":
            raise HTTPException(
                503, "Payments are disabled; records remain available for authorized review"
            )
        if booking.provider != self.provider.kind:
            conflict("Booking provider mode cannot change")
        amounts = (
            booking.duration_days,
            booking.daily_rate_paise,
            booking.rental_fee_paise,
            booking.security_deposit_paise,
            booking.total_amount_paise,
        )
        if (
            any(type(value) is not int for value in amounts)
            or not 0 < booking.duration_days <= 3650
            or booking.daily_rate_paise <= 0
            or booking.security_deposit_paise < 0
            or booking.rental_fee_paise != booking.duration_days * booking.daily_rate_paise
            or booking.total_amount_paise
            != booking.rental_fee_paise + booking.security_deposit_paise
            or not 0 < booking.total_amount_paise <= MAX_AMOUNT_PAISE
            or booking.currency != "INR"
        ):
            conflict("Invalid integer-paise INR booking snapshot")

    def view(self, booking):
        db = self.db
        db.flush()
        from app.services.rating_eligibility import rating_eligible

        refund = db.scalar(select(RefundIntent).where(RefundIntent.booking_id == booking.id))
        dispute = db.scalar(select(RentalDispute).where(RentalDispute.booking_id == booking.id))
        transactions = db.scalars(
            select(PaymentTransaction)
            .where(PaymentTransaction.booking_id == booking.id)
            .order_by(PaymentTransaction.created_at)
        ).all()
        lines = db.scalars(
            select(EscrowLedgerEntry)
            .join(JournalTransaction, JournalTransaction.id == EscrowLedgerEntry.journal_id)
            .where(
                EscrowLedgerEntry.booking_id == booking.id, JournalTransaction.status == "posted"
            )
            .order_by(EscrowLedgerEntry.created_at)
        ).all()
        deposit_accounts = {"escrow_deposit_held", "escrow_deposit_frozen"}
        remaining_liability = sum(
            row.amount_paise * (1 if row.entry_type == "CREDIT" else -1)
            for row in lines
            if row.account_type in deposit_accounts
        )
        processed_deposit_refund = (
            min(refund.amount_paise, booking.security_deposit_paise)
            if refund and refund.status == "processed"
            else 0
        )
        processed_compensation = (
            refund.deduction_paise if refund and refund.status == "processed" else 0
        )
        reserved = (
            min(refund.amount_paise, booking.security_deposit_paise)
            if refund and refund.status != "processed"
            else 0
        )
        expected_deposit = (
            booking.security_deposit_paise if booking.payment_status == "captured" else 0
        )
        return {
            "id": booking.id,
            "borrow_request_id": booking.borrow_request_id,
            "borrower_id": booking.borrower_id,
            "lender_id": booking.lender_id,
            "provider": booking.provider,
            "configured_provider": self.provider.kind,
            "operations_enabled": booking.provider == self.provider.kind
            and self.provider.kind != "disabled",
            "test_mode": True,
            "sandbox_only": self.provider.sandbox_only,
            "simulated_escrow": True,
            "booking_status": booking.booking_status,
            "payment_status": booking.payment_status,
            "deposit_state": booking.deposit_state,
            "rating_eligible": rating_eligible(
                db, db.get(BorrowRequest, booking.borrow_request_id), booking
            ),
            "lender_settlement": {
                "mode": "simulated",
                "rental_earnings_payable_paise": booking.rental_fee_paise
                if booking.payment_status == "captured"
                and booking.settlement_kind != "cancellation"
                else 0,
                "compensation_payable_paise": booking.deduction_paise,
                "provider_transfer_verified": False,
            },
            "reconciliation": {
                "original_deposit_paise": expected_deposit,
                "processed_deposit_refund_paise": processed_deposit_refund,
                "allocated_compensation_paise": processed_compensation,
                "remaining_liability_paise": remaining_liability,
                "reserved_refund_paise": reserved,
                "available_unreserved_paise": max(
                    0,
                    remaining_liability
                    - reserved
                    - (refund.deduction_paise if refund and refund.status != "processed" else 0),
                ),
                "balanced": expected_deposit
                == processed_deposit_refund + processed_compensation + remaining_liability,
            },
            "duration_days": booking.duration_days,
            "daily_rate_paise": booking.daily_rate_paise,
            "rental_fee_paise": booking.rental_fee_paise,
            "security_deposit_paise": booking.security_deposit_paise,
            "total_amount_paise": booking.total_amount_paise,
            "currency": booking.currency,
            "deposit_refunded_paise": booking.refunded_paise,
            "deduction_paise": booking.deduction_paise,
            "held_deposit_paise": remaining_liability,
            "handover_unlocked": booking.payment_status == "captured"
            and booking.booking_status in {"funded", "active"},
            "pending_payment_id": next(
                (
                    row.razorpay_payment_id
                    for row in transactions
                    if row.provider == "mock" and row.status == "authorized"
                ),
                None,
            ),
            "refund": self._refund_view(refund),
            "dispute": self._dispute_view(dispute),
            "transactions": [
                {
                    "id": row.id,
                    "type": row.transaction_type,
                    "amount_paise": row.amount_paise,
                    "status": row.status,
                    "created_at": row.created_at,
                }
                for row in transactions
            ],
            "journal": [
                {
                    "journal_id": row.journal_id,
                    "account": row.account_type,
                    "side": row.entry_type,
                    "amount_paise": row.amount_paise,
                    "description": row.description,
                }
                for row in lines
            ],
            "audit": [
                {
                    "id": row.id,
                    "actor_id": row.actor_id,
                    "action": row.action,
                    "details": json.loads(row.details),
                    "created_at": row.created_at,
                }
                for row in db.scalars(
                    select(FinancialAudit)
                    .where(FinancialAudit.booking_id == booking.id)
                    .order_by(FinancialAudit.created_at)
                ).all()
            ],
        }

    @staticmethod
    def _refund_view(row):
        return (
            None
            if row is None
            else {
                "id": row.id,
                "amount_paise": row.amount_paise,
                "deduction_paise": row.deduction_paise,
                "status": row.status,
                "kind": row.kind,
                "error_code": row.error_code,
                "provider_refund_id": row.provider_refund_id,
            }
        )

    @staticmethod
    def _dispute_view(row):
        if row is None:
            return None
        fields = (
            "id",
            "status",
            "claimed_deduction_paise",
            "claim_version",
            "approved_deduction_paise",
            "lender_claim_notes",
            "borrower_response_notes",
            "borrower_accepted",
            "inspection_id",
            "cv_run_id",
            "assessment_id",
            "resolved_by",
            "initiated_by",
            "origin",
            "resolution_reason",
        )
        return {name: getattr(row, name) for name in fields}

    def get(self, booking_id, actor, admin=False):
        with locked(self.db, booking_id) as booking:
            authorize(booking, actor, admin=admin)
            return self.view(booking)

    def order(self, booking_id, actor, *, accepted_terms=None):
        db = self.db
        with locked(db, booking_id) as booking:
            authorize(booking, actor, borrower=True)
            self._mode(booking)
            if accepted_terms is False:
                raise HTTPException(422, "Accept the rental terms before checkout")
            offer = db.get(NegotiationOffer, booking.offer_id)
            if (
                not offer
                or offer.status != OfferStatus.accepted
                or offer.borrow_request_id != booking.borrow_request_id
            ):
                conflict("Accepted rental terms are required before checkout")
            if booking.booking_status != "awaiting_payment":
                conflict("Booking is not awaiting payment")
            if booking.end_date.date() < datetime.utcnow().date():
                conflict("Rental dates have expired; agree a new booking before payment")
            row = db.scalar(
                select(PaymentTransaction).where(
                    PaymentTransaction.idempotency_key == "order:" + booking.id
                )
            )
            if row and (
                row.amount_paise != booking.total_amount_paise
                or row.currency != "INR"
                or row.provider != booking.provider
                or row.transaction_type != "order"
            ):
                conflict("Stored order does not match the booking snapshot")
            if row and row.status == "ready":
                return self._order_view(row)
            reconcile = row is not None and row.status != "rejected"
            if row is None:
                audit(
                    db,
                    booking,
                    actor,
                    "checkout_terms_accepted",
                    source="checkout_confirmation"
                    if accepted_terms is True
                    else "legacy_accepted_offer",
                    offer_id=booking.offer_id,
                    rental_fee_paise=booking.rental_fee_paise,
                    security_deposit_paise=booking.security_deposit_paise,
                    total_amount_paise=booking.total_amount_paise,
                )
                row = PaymentTransaction(
                    id=str(uuid4()),
                    booking_id=booking.id,
                    provider=booking.provider,
                    transaction_type="order",
                    amount_paise=booking.total_amount_paise,
                    idempotency_key="order:" + booking.id,
                    status="dispatching",
                )
                db.add(row)
                db.flush()
            elif row.status == "rejected":
                row.operation_version += 1
                row.status, row.error_code = "dispatching", None
            reference = row.id
            version = row.operation_version
            snapshot = SimpleNamespace(id=booking.id, total_amount_paise=booking.total_amount_paise)
        try:
            result = (
                self.provider.find_order(reference)
                if reconcile and self.provider.kind != "mock"
                else self.provider.create_order(snapshot, reference)
            )
            if (
                result.get("receipt") != reference
                or type(result.get("amount")) is not int
                or result.get("amount") != snapshot.total_amount_paise
                or result.get("currency") != "INR"
                or result.get("livemode") is True
                or not isinstance(result.get("id"), str)
            ):
                raise ProviderError("order_mismatch")
        except ProviderError as exc:
            with locked(db, booking_id):
                row = db.get(PaymentTransaction, reference)
                if row.operation_version == version and row.status != "ready":
                    row.status, row.error_code = "rejected" if exc.definite else "unknown", exc.code
            raise HTTPException(503, exc.code) from None
        with locked(db, booking_id) as booking:
            row = db.get(PaymentTransaction, reference)
            if row.operation_version != version:
                conflict("Order operation was superseded; inspect its current status")
            if row.status == "ready":
                if row.razorpay_order_id != result["id"]:
                    conflict("Conflicting provider orders require administrator review")
                return self._order_view(row)
            row.razorpay_order_id, row.raw_response, row.status = (
                result["id"],
                json.dumps(
                    {
                        name: result.get(name)
                        for name in ("id", "receipt", "amount", "currency", "status")
                    }
                ),
                "ready",
            )
            if booking.payment_status == "unpaid":
                booking.payment_status = "order_created"
            audit(db, booking, actor, "order_ready", operation_id=reference)
            return self._order_view(row)

    def _order_view(self, row):
        from app.models import User

        booking = self.db.get(RentalBooking, row.booking_id)
        customer = self.db.get(User, booking.borrower_id)
        prefill = (
            {"name": customer.name, "email": customer.email}
            if customer and customer.is_verified
            else {}
        )
        return {
            "order_id": row.razorpay_order_id,
            "amount_paise": row.amount_paise,
            "currency": "INR",
            "booking_id": row.booking_id,
            "provider": row.provider,
            "key_id": self.provider.key_id,
            "test_mode": True,
            "sandbox_only": self.provider.sandbox_only,
            "simulated_escrow": True,
            "prefill": prefill,
        }

    def _capture(self, booking, payment, actor):
        db = self.db
        if not isinstance(payment.get("id"), str) or payment.get("status") not in {
            "created",
            "authorized",
            "failed",
            "captured",
        }:
            conflict("Unsupported payment result; reconciliation required")
        order = db.scalar(
            select(PaymentTransaction).where(
                PaymentTransaction.booking_id == booking.id,
                PaymentTransaction.transaction_type == "order",
            )
        )
        if (
            not order
            or payment.get("order_id") != order.razorpay_order_id
            or type(payment.get("amount")) is not int
            or payment["amount"] != booking.total_amount_paise
            or payment.get("currency") != "INR"
            or payment.get("livemode") is True
            or (payment.get("status") == "captured" and payment.get("captured") is False)
        ):
            conflict("Payment does not match the immutable booking/order")
        row = db.scalar(
            select(PaymentTransaction).where(
                PaymentTransaction.razorpay_payment_id == payment["id"]
            )
        )
        if row and row.booking_id != booking.id:
            conflict("Payment already belongs to another booking")
        if booking.payment_status == "captured":
            if payment["status"] != "captured":
                return  # A late authorized/failed event cannot reverse confirmed funding.
            existing = db.scalar(
                select(PaymentTransaction).where(
                    PaymentTransaction.booking_id == booking.id,
                    PaymentTransaction.transaction_type == "payment",
                    PaymentTransaction.status == "captured",
                )
            )
            if not existing or existing.razorpay_payment_id != payment["id"]:
                conflict("Another payment already funded this booking")
            return
        if row is None:
            row = PaymentTransaction(
                booking_id=booking.id,
                provider=booking.provider,
                transaction_type="payment",
                amount_paise=booking.total_amount_paise,
                idempotency_key="payment:" + payment["id"],
                razorpay_payment_id=payment["id"],
                razorpay_order_id=payment["order_id"],
            )
            db.add(row)
        row.status, row.raw_response = (
            payment["status"],
            json.dumps(
                {
                    name: payment.get(name)
                    for name in ("id", "order_id", "amount", "currency", "status")
                }
            ),
        )
        if payment["status"] != "captured":
            booking.payment_status = "authorized" if payment["status"] == "authorized" else "failed"
            return
        late_cancel = booking.booking_status == "cancelled"
        post(
            db,
            booking,
            "funding:" + booking.id,
            [
                ("gateway_clearing", "DEBIT", booking.total_amount_paise),
                ("rental_fee_clearing", "CREDIT", booking.rental_fee_paise),
                ("escrow_deposit_held", "CREDIT", booking.security_deposit_paise),
            ],
            "TEST MODE: payment funding; simulated accounting",
        )
        booking.payment_status, booking.booking_status, booking.deposit_state = (
            "captured",
            "funded",
            "held",
        )
        audit(db, booking, actor, "payment_captured", payment_id=payment["id"])
        if late_cancel:
            # A previously authorized cancellation also covers late provider confirmation.
            self._intent(booking, "cancellation", 0, booking.borrower_id)

    def demo_pay(self, booking_id, actor, outcome, payment_id=None):
        if self.provider.kind != "mock":
            raise HTTPException(403, "Demo actions are unavailable for Razorpay")
        with locked(self.db, booking_id) as booking:
            authorize(booking, actor, borrower=True)
            self._mode(booking)
            if booking.payment_status == "captured":
                return self.view(booking)
            if booking.booking_status != "awaiting_payment":
                conflict("Booking is not payable")
            order = self.db.scalar(
                select(PaymentTransaction).where(
                    PaymentTransaction.booking_id == booking.id,
                    PaymentTransaction.transaction_type == "order",
                    PaymentTransaction.status == "ready",
                )
            )
            if not order:
                conflict("Create an order first")
            pending = self.db.scalar(
                select(PaymentTransaction).where(
                    PaymentTransaction.booking_id == booking.id,
                    PaymentTransaction.status == "authorized",
                )
            )
            if pending and payment_id is None:
                result = self.view(booking)
                result["pending_payment_id"] = pending.razorpay_payment_id
                return result
            if payment_id and (not pending or pending.razorpay_payment_id != payment_id):
                conflict("Unknown pending mock attempt")
            attempt = payment_id.removeprefix("pay_mock_") if payment_id else str(uuid4())
            payment = self.provider.demo_payment(json.loads(order.raw_response), outcome, attempt)
            self._capture(booking, payment, actor)
            if outcome == "cancelled":
                audit(self.db, booking, actor, "mock_checkout_cancelled")
            self.db.flush()
            result = self.view(booking)
            result["pending_payment_id"] = payment["id"] if outcome == "pending" else None
            return result

    def verify(self, booking_id, actor, order_id, payment_id, signature=None, reconcile=False):
        with locked(self.db, booking_id) as booking:
            authorize(booking, actor, borrower=True)
            self._mode(booking)
            if self.provider.kind == "mock":
                raise HTTPException(409, "Use the explicit demo checkout")
            row = self.db.scalar(
                select(PaymentTransaction).where(
                    PaymentTransaction.booking_id == booking.id,
                    PaymentTransaction.transaction_type == "order",
                )
            )
            if not row or row.razorpay_order_id != order_id:
                conflict("Wrong order association")
            reference, amount = row.id, booking.total_amount_paise
            if not reconcile and not self.provider.verify_checkout(
                row.razorpay_order_id, payment_id, signature
            ):
                raise HTTPException(400, "Invalid checkout signature")
        try:
            order, payment = (
                self.provider.fetch_order(order_id),
                self.provider.fetch_payment(payment_id),
            )
        except ProviderError as exc:
            raise HTTPException(503, exc.code) from None
        if (
            order.get("id") != order_id
            or order.get("receipt") != reference
            or type(order.get("amount")) is not int
            or order.get("amount") != amount
            or order.get("currency") != "INR"
            or order.get("livemode") is True
            or payment.get("id") != payment_id
        ):
            conflict("Authoritative provider data does not match booking")
        with locked(self.db, booking_id) as booking:
            self._capture(booking, payment, actor)
            self.db.flush()
            return self.view(booking)

    def _intent(self, booking, kind, deduction, actor):
        db = self.db
        existing = db.scalar(select(RefundIntent).where(RefundIntent.booking_id == booking.id))
        if existing:
            if existing.kind != kind or existing.deduction_paise != deduction:
                conflict("Settlement is already authorized with different terms")
            return existing
        if (
            booking.payment_status != "captured"
            or type(deduction) is not int
            or not 0 <= deduction <= booking.security_deposit_paise
        ):
            conflict("Invalid settlement allocation")
        amount = booking.security_deposit_paise - deduction
        if kind == "cancellation":
            amount += booking.rental_fee_paise
        row = RefundIntent(
            booking_id=booking.id,
            amount_paise=amount,
            deduction_paise=deduction,
            kind=kind,
            authorized_by=actor,
        )
        db.add(row)
        db.flush()
        booking.settlement_kind, booking.booking_status = kind, "settling"
        booking.deposit_state = "refund_pending"
        audit(
            db, booking, actor, "settlement_authorized", refund_id=row.id, deduction_paise=deduction
        )
        return row

    def clean_return(self, booking_id, actor):
        with locked(self.db, booking_id) as booking:
            authorize(booking, actor, lender=True)
            request = self.db.get(BorrowRequest, booking.borrow_request_id)
            if request.handover_status != "return_confirmed" or request.disputed_at:
                conflict("Lender-approved undisputed physical return is required")
            if self.db.scalar(select(RentalDispute).where(RentalDispute.booking_id == booking.id)):
                conflict("Dispute resolution is required")
            row = self._intent(booking, "clean_return", 0, actor)
            return self._refund_view(row)

    def cancel(self, booking_id, actor):
        with locked(self.db, booking_id) as booking:
            authorize(booking, actor)
            request = self.db.get(BorrowRequest, booking.borrow_request_id)
            if (
                request.handover_status not in {"pending", "photos_uploaded", "issue_reported"}
                or request.borrowing_started_at
            ):
                conflict(
                    "Only pre-receipt cancellation is permitted; active rentals require return review"
                )
            if booking.booking_status in {"completed", "disputed"}:
                conflict("Booking cannot be cancelled")
            request.status = BorrowRequestStatus.cancelled
            self.db.get(NegotiationOffer, booking.offer_id).status = OfferStatus.cancelled
            audit(self.db, booking, actor, "cancellation_authorized")
            if booking.payment_status == "captured":
                row = self._intent(booking, "cancellation", 0, actor)
                return self._refund_view(row)
            booking.booking_status = "cancelled"
            return {"status": "cancelled", "refund": None}

    def claim(self, booking_id, actor, amount, notes, references=None, draft=False):
        with locked(self.db, booking_id) as booking:
            authorize(booking, actor, lender=True)
            request = self.db.get(BorrowRequest, booking.borrow_request_id)
            if (
                booking.payment_status != "captured"
                or booking.settlement_kind
                or type(amount) is not int
                or not notes.strip()
                or request.handover_status not in {"return_photos_uploaded", "return_confirmed"}
                or not request.returned_at
                or not 0 <= amount <= booking.security_deposit_paise
            ):
                conflict("Claim not eligible or above deposit")
            row = self.db.scalar(
                select(RentalDispute).where(RentalDispute.booking_id == booking.id)
            )
            if row and (row.status not in {"raised", "needs_claim"} or row.borrower_accepted):
                conflict("Claim is already under an accepted resolution")
            notes = notes.strip()
            reference_values = {}
            for name in ("inspection_id", "cv_run_id", "assessment_id"):
                value = (references or {}).get(name)
                reference_values[name] = str(value) if value else None
            target_status = "needs_claim" if draft else "raised"
            if (
                row is not None
                and row.status == target_status
                and row.claimed_deduction_paise == amount
                and row.lender_claim_notes == notes
                and all(getattr(row, name) == value for name, value in reference_values.items())
            ):
                # A lost response/repeated click acknowledges the existing version;
                # it must not invalidate consent or append another submission audit.
                return self._dispute_view(row)
            if row is not None:
                row.claim_version += 1
            row = self._freeze(booking, request, actor, notes, "lender_claim")
            row.claimed_deduction_paise, row.lender_claim_notes = amount, notes
            row.status = target_status
            for name, value in reference_values.items():
                setattr(row, name, value)
            request.disputed_at, request.dispute_description = datetime.utcnow(), notes
            booking.deposit_state, booking.booking_status = "frozen", "disputed"
            audit(
                self.db,
                booking,
                actor,
                "claim_submitted",
                requested_paise=amount,
                reason=notes,
                claim_version=row.claim_version,
            )
            self.db.flush()
            return self._dispute_view(row)

    def _freeze(self, booking, request, actor, notes, origin, status="needs_claim"):
        if booking.payment_status != "captured" or booking.settlement_kind:
            conflict("Only an unsettled funded booking can enter dispute")
        row = self.db.scalar(select(RentalDispute).where(RentalDispute.booking_id == booking.id))
        if row is None:
            row = RentalDispute(
                booking_id=booking.id,
                lender_claim_notes=notes,
                claimed_deduction_paise=0,
                initiated_by=actor,
                origin=origin,
                status=status,
            )
            self.db.add(row)
            if booking.security_deposit_paise:
                post(
                    self.db,
                    booking,
                    "freeze:" + booking.id,
                    [
                        ("escrow_deposit_held", "DEBIT", booking.security_deposit_paise),
                        ("escrow_deposit_frozen", "CREDIT", booking.security_deposit_paise),
                    ],
                    "TEST MODE: disputed deposit frozen",
                )
        request.disputed_at = request.disputed_at or datetime.utcnow()
        request.dispute_description = notes
        booking.deposit_state, booking.booking_status = "frozen", "disputed"
        return row

    def escalate(self, booking_id, actor, notes, origin="participant_dispute"):
        with locked(self.db, booking_id) as booking:
            authorize(booking, actor)
            request = self.db.get(BorrowRequest, booking.borrow_request_id)
            row = self._freeze(booking, request, actor, notes, origin, status="escalated")
            if row.status in {"settled_mutual", "settled_arbitrated"}:
                conflict("Dispute already resolved")
            row.status, row.borrower_accepted = "escalated", False
            audit(self.db, booking, actor, "dispute_escalated", reason=notes, origin=origin)
            self.db.flush()
            return self._dispute_view(row)

    def return_decision(self, booking_id, actor, approved, notes=""):
        # Physical decision and financial authorization share one local commit.
        with locked(self.db, booking_id) as booking:
            authorize(booking, actor, lender=True)
            request = self.db.scalar(
                select(BorrowRequest)
                .where(BorrowRequest.id == booking.borrow_request_id)
                .with_for_update()
            )
            if (
                request.handover_status not in {"return_photos_uploaded", "return_confirmed"}
                or not request.returned_at
            ):
                conflict("Borrower return photographs are required")
            if booking.settlement_kind:
                if approved and booking.settlement_kind == "clean_return":
                    return self.view(booking)
                conflict("An existing settlement cannot be replaced by a return decision")
            existing_dispute = self.db.scalar(
                select(RentalDispute).where(RentalDispute.booking_id == booking.id)
            )
            if not approved and existing_dispute:
                if existing_dispute.status not in {"needs_claim", "raised"}:
                    conflict("Dispute already escalated or resolved")
                return self.view(booking)  # Rejection already recorded; claim revisions use /raise.
            request.return_condition_note = notes
            if approved:
                if request.disputed_at or self.db.scalar(
                    select(RentalDispute).where(RentalDispute.booking_id == booking.id)
                ):
                    conflict("Platform dispute resolution is required")
                request.handover_status = "return_confirmed"
                request.return_confirmed_at, request.return_confirmed_by = datetime.utcnow(), actor
                self._intent(booking, "clean_return", 0, actor)
                audit(self.db, booking, actor, "return_approved", reason=notes)
            else:
                row = self._freeze(
                    booking,
                    request,
                    actor,
                    notes or "Return condition rejected",
                    "return_rejection",
                )
                if row.status not in {"needs_claim", "raised"}:
                    conflict("Dispute already escalated or resolved")
                audit(self.db, booking, actor, "return_rejected", reason=notes)
            self.db.flush()
            return self.view(booking)

    def resolve_issue(self, booking_id, actor, action, reason, admin=False):
        with locked(self.db, booking_id) as booking:
            authorize(booking, actor, lender=True, admin=admin)
            request = self.db.get(BorrowRequest, booking.borrow_request_id)
            dispute = self.db.scalar(
                select(RentalDispute).where(RentalDispute.booking_id == booking.id)
            )
            recovering_dispute = dispute is not None and booking.booking_status == "disputed"
            if booking.settlement_kind or (
                request.handover_status != "issue_reported" and not recovering_dispute
            ):
                conflict("No unresolved handover issue")
            if recovering_dispute and (
                not admin or actor in {booking.borrower_id, booking.lender_id}
            ):
                raise HTTPException(403, "Independent administrator recovery is required")
            if not reason.strip():
                raise HTTPException(422, "A resolution reason is required")
            if action == "continue":
                if not admin:
                    raise HTTPException(
                        403, "Platform review is required to resume a reported issue"
                    )
                if booking.booking_status == "disputed":
                    conflict("Resolve the financial dispute before continuing")
                request.handover_status = (
                    "borrower_confirmed" if request.handover_confirmed_at else "photos_uploaded"
                )
            elif action == "cancel":
                if not admin:
                    raise HTTPException(403, "Platform confirmation of item recovery is required")
                if (
                    request.borrowing_started_at
                    or (recovering_dispute and request.handover_confirmed_at)
                    or (not recovering_dispute and request.disputed_at)
                    or request.handover_status
                    not in {"pending", "photos_uploaded", "issue_reported"}
                ):
                    conflict(
                        "Received/active rentals require physical return and platform settlement"
                    )
                self._intent(booking, "cancellation", 0, actor)
                if recovering_dispute:
                    dispute.status = "settled_arbitrated"
                    dispute.approved_deduction_paise = 0
                    dispute.resolved_by, dispute.resolved_at = actor, datetime.utcnow()
                    dispute.resolution_reason = reason.strip()
                    audit(
                        self.db,
                        booking,
                        actor,
                        "dispute_resolved",
                        reason=reason.strip(),
                        approved_deduction_paise=0,
                        authority="administrator",
                        policy="existing_pre_receipt_cancellation",
                    )
                request.status = BorrowRequestStatus.cancelled
                self.db.get(NegotiationOffer, booking.offer_id).status = OfferStatus.cancelled
            elif action == "return":
                if not admin:
                    raise HTTPException(403, "Platform review is required")
                if request.returned_at or (
                    recovering_dispute
                    and not request.handover_confirmed_at
                    and not request.borrowing_started_at
                ):
                    conflict("Return recovery requires a received item without an existing return")
                request.handover_status = "lender_confirmed"
                request.borrowing_started_at = request.borrowing_started_at or datetime.utcnow()
                booking.booking_status = (
                    "active" if booking.booking_status != "disputed" else "disputed"
                )
            else:
                raise HTTPException(422, "Unsupported issue resolution")
            audit(
                self.db, booking, actor, "handover_issue_resolved", resolution=action, reason=reason
            )
            return self.view(booking)

    def respond(self, booking_id, actor, accepted, notes, claim_version):
        with locked(self.db, booking_id) as booking:
            authorize(booking, actor, borrower=True)
            row = self.db.scalar(
                select(RentalDispute).where(RentalDispute.booking_id == booking.id)
            )
            if not row or row.status != "raised":
                conflict("No open claim")
            if claim_version != row.claim_version:
                conflict("Claim changed; review its current amount and evidence before responding")
            row.borrower_accepted, row.borrower_response_notes = accepted, notes
            if not accepted:
                row.status = "escalated"
                audit(self.db, booking, actor, "dispute_escalated", reason=notes)
            audit(
                self.db,
                booking,
                actor,
                "claim_response",
                accepted=accepted,
                notes=notes,
                claim_version=claim_version,
                claimed_deduction_paise=row.claimed_deduction_paise,
            )
            return self._dispute_view(row)

    def resolve(self, booking_id, actor, amount, admin=False, reason="", claim_version=None):
        with locked(self.db, booking_id) as booking:
            authorize(booking, actor, admin=admin)
            if not admin or actor in {booking.borrower_id, booking.lender_id}:
                raise HTTPException(
                    403, "An independent human administrator must review deductions"
                )
            if not reason.strip():
                raise HTTPException(422, "Administrator resolution requires a reason")
            request = self.db.get(BorrowRequest, booking.borrow_request_id)
            if (
                request.handover_status not in {"return_photos_uploaded", "return_confirmed"}
                or not request.returned_at
                or not request.return_photos
            ):
                conflict("Physical return evidence is required before dispute settlement")
            row = self.db.scalar(
                select(RentalDispute).where(RentalDispute.booking_id == booking.id)
            )
            if not row or row.status not in {
                "raised",
                "needs_claim",
                "escalated",
                "settled_mutual",
                "settled_arbitrated",
            }:
                conflict("No claim to resolve")
            # Version-one legacy clients remain compatible; revised claims must
            # explicitly identify the version the administrator actually reviewed.
            if (claim_version if claim_version is not None else 1) != row.claim_version:
                conflict("Claim changed; refresh and review the current claim version")
            if type(amount) is not int or not 0 <= amount <= booking.security_deposit_paise:
                conflict("Deduction exceeds deposit")
            if row.resolved_at:
                if row.approved_deduction_paise != amount:
                    conflict("The recorded resolution is immutable")
                return self._refund_view(
                    self.db.scalar(
                        select(RefundIntent).where(RefundIntent.booking_id == booking.id)
                    )
                )
            intent = self._intent(booking, "dispute", amount, actor)
            row.status = "settled_arbitrated"
            row.approved_deduction_paise, row.resolved_by, row.resolved_at = (
                amount,
                actor,
                datetime.utcnow(),
            )
            row.resolution_reason = reason.strip()
            audit(
                self.db,
                booking,
                actor,
                "dispute_resolved",
                reason=row.resolution_reason,
                approved_deduction_paise=amount,
                claim_version=row.claim_version,
                authority="administrator",
                evidence_references={
                    "return_photos": json.loads(request.return_photos),
                    "inspection_id": row.inspection_id,
                    "cv_run_id": row.cv_run_id,
                    "assessment_id": row.assessment_id,
                },
            )
            return self._refund_view(intent)

    def execute_refund(
        self, booking_id, actor, demo_outcome="processed", admin=False, *, allow_dispatch=True
    ):
        # Verified gateway webhooks may reconcile existing outcomes with GETs.
        # Every dispatch, including mock settlement, requires a real admin actor.
        if allow_dispatch or self.provider.kind == "mock":
            self._refund_admin(actor, admin)
        db = self.db
        with locked(db, booking_id) as booking:
            authorize(booking, actor, admin=admin)
            self._mode(booking)
            row = db.scalar(select(RefundIntent).where(RefundIntent.booking_id == booking.id))
            if not row:
                conflict("An authorized settlement intent is required")
            if row.status == "processed":
                return self.view(booking)
            if row.status == "dispatching":
                conflict("Refund dispatch is active; reconcile before retry")
            expected = booking.security_deposit_paise - row.deduction_paise
            if row.kind == "cancellation":
                expected += booking.rental_fee_paise
            if (
                row.kind != booking.settlement_kind
                or row.amount_paise != expected
                or not 0 <= row.deduction_paise <= booking.security_deposit_paise
                or booking.payment_status != "captured"
            ):
                conflict("Refund allocation integrity failed")
            payment = db.scalar(
                select(PaymentTransaction).where(
                    PaymentTransaction.booking_id == booking.id,
                    PaymentTransaction.transaction_type == "payment",
                    PaymentTransaction.status == "captured",
                )
            )
            if not payment:
                conflict("No captured payment")
            if (
                not allow_dispatch
                and self.provider.kind == "razorpay_test"
                and row.status == "created"
                and not row.provider_refund_id
            ):
                # Clean-return approval creates an intent, not a gateway request.
                # Reading an unsent intent must not invent a dispatch attempt or
                # turn the absence of a gateway refund into an unknown outcome.
                return self.view(booking)
            rid, reference, amount, pid, existing_id = (
                row.id,
                row.idempotency_key,
                row.amount_paise,
                payment.razorpay_payment_id,
                row.provider_refund_id,
            )
            row.status = "dispatching"
            attempt = RefundAttempt(refund_id=rid, status="dispatching", idempotency_key=reference)
            db.add(attempt)
            db.flush()
            attempt_id = attempt.id
            row.active_attempt_id = attempt_id
            status_check = self.provider.kind == "razorpay_test" and (
                bool(existing_id) or not allow_dispatch
            )
            audit(
                db, booking, actor,
                "refund_status_check_requested" if status_check else "refund_requested",
                refund_id=rid, attempt_id=attempt_id,
            )
        try:
            if amount == 0:
                result = {"id": None, "payment_id": pid, "amount": 0, "status": "processed"}
            elif existing_id and self.provider.kind != "mock":
                result = self.provider.fetch_refund(existing_id)
            elif not allow_dispatch and self.provider.kind == "razorpay_test":
                result = self.provider.find_refund(pid, reference)
            else:
                result = self.provider.refund(pid, amount, reference)
            if self.provider.kind == "mock":
                result["status"] = demo_outcome
            if (
                result.get("payment_id") != pid
                or type(result.get("amount")) is not int
                or result["amount"] != amount
                or (amount > 0 and result.get("currency") != "INR")
                or (amount > 0 and not isinstance(result.get("id"), str))
                or (
                    amount > 0
                    and self.provider.kind == "razorpay_test"
                    and not re.fullmatch(r"rfnd_[A-Za-z0-9]{1,123}", result.get("id", ""))
                )
                or (result.get("receipt") is not None and result["receipt"] != reference)
                or result.get("livemode") is True
                or (existing_id and result.get("id") != existing_id)
                or result.get("status") not in {"pending", "processed", "failed"}
            ):
                raise ProviderError("refund_mismatch")
        except ProviderError as exc:
            with locked(db, booking_id) as booking:
                row = db.get(RefundIntent, rid)
                if row.status == "processed" or row.active_attempt_id != attempt_id:
                    return self.view(booking)
                row.status, row.error_code = "unknown", exc.code
                db.get(RefundAttempt, attempt_id).status = "unknown"
                db.get(RefundAttempt, attempt_id).error_code = exc.code
                audit(db, booking, actor, "refund_unknown", refund_id=rid, error_code=exc.code)
            raise HTTPException(503, exc.code) from None
        with locked(db, booking_id) as booking:
            row = db.get(RefundIntent, rid)
            if row.status == "processed" or row.active_attempt_id != attempt_id:
                return self.view(booking)
            other = (
                db.scalar(
                    select(PaymentTransaction).where(
                        PaymentTransaction.razorpay_refund_id == result.get("id"),
                        PaymentTransaction.idempotency_key != "refund:" + reference,
                    )
                )
                if amount
                else None
            )
            if other:
                row.status, row.error_code = "unknown", "refund_identifier_conflict"
                db.get(RefundAttempt, attempt_id).status = "unknown"
                audit(
                    db,
                    booking,
                    actor,
                    "refund_unknown",
                    refund_id=rid,
                    error_code="refund_identifier_conflict",
                )
                return self.view(booking)
            row.status, row.provider_refund_id, row.error_code = (
                result["status"],
                result.get("id"),
                None,
            )
            db.get(RefundAttempt, attempt_id).status = result["status"]
            db.get(RefundAttempt, attempt_id).provider_refund_id = result.get("id")
            if result["status"] == "failed":
                audit(db, booking, actor, "refund_failed", refund_id=rid)
            else:
                audit(
                    db,
                    booking,
                    actor,
                    "refund_reconciled",
                    refund_id=rid,
                    provider_status=result["status"],
                    provider_refund_id=result.get("id"),
                )
            if amount:
                transaction = db.scalar(
                    select(PaymentTransaction).where(
                        PaymentTransaction.idempotency_key == "refund:" + reference
                    )
                )
                if transaction is None:
                    transaction = PaymentTransaction(
                        booking_id=booking.id,
                        provider=booking.provider,
                        transaction_type="deposit_refund",
                        amount_paise=amount,
                        idempotency_key="refund:" + reference,
                        razorpay_refund_id=result.get("id"),
                    )
                    db.add(transaction)
                transaction.status = result["status"]
                transaction.razorpay_refund_id = result.get("id")
            if result["status"] == "processed":
                frozen = db.scalar(
                    select(RentalDispute).where(RentalDispute.booking_id == booking.id)
                )
                source = "escrow_deposit_frozen" if frozen else "escrow_deposit_held"
                post(
                    db,
                    booking,
                    "settlement:" + booking.id,
                    [
                        (source, "DEBIT", booking.security_deposit_paise),
                        ("rental_fee_clearing", "DEBIT", booking.rental_fee_paise),
                        ("gateway_clearing", "CREDIT", amount),
                        (
                            "lender_receivable_simulated",
                            "CREDIT",
                            booking.total_amount_paise - amount,
                        ),
                    ],
                    "TEST MODE: confirmed refund and simulated lender allocation; no payout",
                )
                booking.refunded_paise = booking.security_deposit_paise - row.deduction_paise
                booking.deduction_paise = row.deduction_paise
                booking.deposit_state = "settled"
                booking.booking_status = "cancelled" if row.kind == "cancellation" else "completed"
                req = db.get(BorrowRequest, booking.borrow_request_id)
                req.status = (
                    BorrowRequestStatus.cancelled
                    if row.kind == "cancellation"
                    else BorrowRequestStatus.closed
                )
                audit(db, booking, actor, "settlement_confirmed", refund_id=rid)
            return self.view(booking)

    def reconcile_refund(self, booking_id, actor, demo_outcome="processed", admin=False):
        if self.provider.kind == "mock":
            self._refund_admin(actor, admin)
        # Crash recovery preserves the same provider idempotency key and exact payload.
        with locked(self.db, booking_id) as booking:
            authorize(booking, actor, admin=admin)
            row = self.db.scalar(select(RefundIntent).where(RefundIntent.booking_id == booking.id))
            if row and row.status == "dispatching":
                # Do not race a live dispatch: require operator review after the 30-second lease.
                latest = self.db.scalar(
                    select(RefundAttempt)
                    .where(RefundAttempt.refund_id == row.id)
                    .order_by(RefundAttempt.created_at.desc())
                )
                if latest and (datetime.utcnow() - latest.created_at).total_seconds() < 30:
                    conflict("Refund is still dispatching")
                row.status = "unknown"
        return self.execute_refund(
            booking_id, actor, demo_outcome, admin=admin, allow_dispatch=False
        )

    def retry_failed_refund(self, booking_id, actor, admin=False):
        self._refund_admin(actor, admin)
        if not admin or self.provider.kind != "razorpay_test":
            raise HTTPException(403, "Confirmed failed gateway refunds require administrator retry")
        with locked(self.db, booking_id) as booking:
            self._mode(booking)
            row = self.db.scalar(select(RefundIntent).where(RefundIntent.booking_id == booking.id))
            if not row or row.status != "failed" or not row.provider_refund_id:
                conflict("A known failed gateway refund is required")
            refund_id, old_id, amount = row.id, row.provider_refund_id, row.amount_paise
            payment = self.db.scalar(
                select(PaymentTransaction).where(
                    PaymentTransaction.booking_id == booking.id,
                    PaymentTransaction.transaction_type == "payment",
                    PaymentTransaction.status == "captured",
                )
            )
            payment_id = payment.razorpay_payment_id
        try:
            confirmed = self.provider.fetch_refund(old_id)
        except ProviderError as exc:
            raise HTTPException(503, exc.code) from None
        if (
            confirmed.get("id") != old_id
            or confirmed.get("status") != "failed"
            or confirmed.get("amount") != amount
            or type(confirmed.get("amount")) is not int
            or confirmed.get("currency") != "INR"
            or confirmed.get("livemode") is True
            or confirmed.get("payment_id") != payment_id
        ):
            conflict("Gateway has not confirmed terminal refund failure")
        with locked(self.db, booking_id) as booking:
            row = self.db.get(RefundIntent, refund_id)
            if row.status != "failed" or row.provider_refund_id != old_id:
                conflict("Refund state changed before administrator retry")
            audit(
                self.db, booking, actor, "failed_refund_retry_authorized", previous_refund_id=old_id
            )
            row.idempotency_key, row.provider_refund_id, row.status = str(uuid4()), None, "created"
        return self.execute_refund(booking_id, actor, admin=True)
