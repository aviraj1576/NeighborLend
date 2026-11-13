"""Additive payment domain. Values are integer paise; gateway records are not escrow."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    event,
    inspect,
)

from app.database import Base


def key():
    return str(uuid4())


class RentalBooking(Base):
    __tablename__ = "rental_bookings"
    id = Column(String(36), primary_key=True, default=key)
    borrow_request_id = Column(
        String, ForeignKey("borrow_requests.id"), unique=True, nullable=False
    )
    offer_id = Column(String, ForeignKey("negotiation_offers.id"), unique=True, nullable=False)
    listing_id = Column(String, ForeignKey("listings.id"), nullable=False)
    borrower_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    lender_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    duration_days = Column(Integer, nullable=False)
    daily_rate_paise = Column(BigInteger, nullable=False)
    rental_fee_paise = Column(BigInteger, nullable=False)
    security_deposit_paise = Column(BigInteger, nullable=False)
    total_amount_paise = Column(BigInteger, nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    provider = Column(String(20), nullable=False)
    booking_status = Column(String(32), nullable=False, default="awaiting_payment")
    payment_status = Column(String(32), nullable=False, default="unpaid")
    deposit_state = Column(String(32), nullable=False, default="unfunded")
    refunded_paise = Column(BigInteger, nullable=False, default=0)
    deduction_paise = Column(BigInteger, nullable=False, default=0)
    settlement_kind = Column(String(32), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        CheckConstraint("duration_days > 0 AND daily_rate_paise > 0 AND rental_fee_paise > 0"),
        CheckConstraint(
            "security_deposit_paise >= 0 AND total_amount_paise = rental_fee_paise + security_deposit_paise"
        ),
        CheckConstraint(
            "refunded_paise >= 0 AND deduction_paise >= 0 AND refunded_paise + deduction_paise <= security_deposit_paise"
        ),
        CheckConstraint("currency = 'INR' AND provider IN ('mock', 'razorpay_test')"),
        CheckConstraint(
            "booking_status IN ('awaiting_payment','funded','active','returned','disputed','settling','completed','cancelled')"
        ),
        CheckConstraint(
            "payment_status IN ('unpaid','order_created','authorized','captured','failed')"
        ),
    )


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"
    id = Column(String(36), primary_key=True, default=key)
    booking_id = Column(String, ForeignKey("rental_bookings.id"), nullable=False, index=True)
    provider = Column(String(20), nullable=False)
    transaction_type = Column(String(32), nullable=False)
    amount_paise = Column(BigInteger, nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    status = Column(String(32), nullable=False, default="created")
    idempotency_key = Column(String(128), unique=True, nullable=False)
    razorpay_order_id = Column(String(128), nullable=True, index=True)
    razorpay_payment_id = Column(String(128), nullable=True, unique=True)
    razorpay_refund_id = Column(String(128), nullable=True, unique=True)
    error_code = Column(String(64), nullable=True)
    operation_version = Column(Integer, nullable=False, default=1)
    raw_response = Column(
        Text, nullable=True
    )  # Minimal normalized provider data, never credentials.
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (CheckConstraint("amount_paise > 0 AND currency = 'INR'"),)


class JournalTransaction(Base):
    __tablename__ = "journal_transactions"
    id = Column(String(36), primary_key=True, default=key)
    booking_id = Column(String, ForeignKey("rental_bookings.id"), nullable=False, index=True)
    reference = Column(String(128), nullable=False, unique=True)
    status = Column(String(10), nullable=False, default="draft")
    debit_paise = Column(BigInteger, nullable=False)
    credit_paise = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (CheckConstraint("debit_paise = credit_paise AND debit_paise > 0"),)


class EscrowLedgerEntry(Base):
    __tablename__ = "escrow_ledger_entries"
    id = Column(String(36), primary_key=True, default=key)
    journal_id = Column(String, ForeignKey("journal_transactions.id"), nullable=False, index=True)
    booking_id = Column(String, ForeignKey("rental_bookings.id"), nullable=False, index=True)
    account_type = Column(String(40), nullable=False)
    entry_type = Column(String(6), nullable=False)
    amount_paise = Column(BigInteger, nullable=False)
    description = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (CheckConstraint("amount_paise > 0 AND entry_type IN ('DEBIT','CREDIT')"),)


class RefundIntent(Base):
    __tablename__ = "refund_intents"
    id = Column(String(36), primary_key=True, default=key)
    booking_id = Column(String, ForeignKey("rental_bookings.id"), nullable=False, unique=True)
    amount_paise = Column(BigInteger, nullable=False)
    deduction_paise = Column(BigInteger, nullable=False, default=0)
    kind = Column(String(32), nullable=False)
    authorized_by = Column(String, ForeignKey("users.id"), nullable=False)
    status = Column(String(32), nullable=False, default="created")
    provider_refund_id = Column(String(128), nullable=True, unique=True)
    idempotency_key = Column(String(128), nullable=False, unique=True, default=key)
    error_code = Column(String(64), nullable=True)
    active_attempt_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (CheckConstraint("amount_paise >= 0 AND deduction_paise >= 0"),)


class RefundAttempt(Base):
    __tablename__ = "refund_attempts"
    id = Column(String(36), primary_key=True, default=key)
    refund_id = Column(String, ForeignKey("refund_intents.id"), nullable=False, index=True)
    provider_refund_id = Column(String(128), nullable=True, index=True)
    idempotency_key = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False)
    error_code = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class RentalDispute(Base):
    __tablename__ = "rental_disputes"
    id = Column(String(36), primary_key=True, default=key)
    booking_id = Column(String, ForeignKey("rental_bookings.id"), nullable=False, unique=True)
    inspection_id = Column(String(64), nullable=True)
    cv_run_id = Column(String(64), nullable=True)
    assessment_id = Column(String(64), nullable=True)
    claimed_deduction_paise = Column(BigInteger, nullable=False)
    claim_version = Column(Integer, nullable=False, default=1)
    approved_deduction_paise = Column(BigInteger, nullable=True)
    status = Column(String(32), nullable=False, default="raised")
    lender_claim_notes = Column(Text, nullable=False)
    borrower_response_notes = Column(Text, nullable=True)
    borrower_accepted = Column(Boolean, nullable=False, default=False)
    resolved_by = Column(String, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    initiated_by = Column(String, nullable=True)
    origin = Column(String(32), nullable=False, default="lender_claim")
    resolution_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        CheckConstraint(
            "claimed_deduction_paise >= 0 AND (approved_deduction_paise IS NULL OR approved_deduction_paise >= 0)"
        ),
    )


class ProcessedWebhook(Base):
    __tablename__ = "processed_webhooks"
    event_id = Column(String(128), primary_key=True)
    event_type = Column(String(64), nullable=False)
    payload_sha256 = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="received")
    payload = Column(Text, nullable=False)
    processed_at = Column(DateTime, nullable=True)


class FinancialAudit(Base):
    __tablename__ = "financial_audit_records"
    id = Column(String(36), primary_key=True, default=key)
    booking_id = Column(String, ForeignKey("rental_bookings.id"), nullable=False, index=True)
    actor_id = Column(String, nullable=False)
    action = Column(String(64), nullable=False)
    details = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class RentalEvidence(Base):
    __tablename__ = "rental_evidence"
    id = Column(String(36), primary_key=True, default=key)
    booking_id = Column(String, ForeignKey("rental_bookings.id"), nullable=False, index=True)
    uploaded_by = Column(String, ForeignKey("users.id"), nullable=False)
    stage = Column(String(24), nullable=False)
    storage_name = Column(String(80), nullable=False, unique=True)
    sha256 = Column(String(64), nullable=False)
    media_type = Column(String(32), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (CheckConstraint("stage IN ('handover','receipt','return')"),)


def immutable(mapper, connection, target):
    raise ValueError("Financial journal and audit records are append-only")


for model in (JournalTransaction, EscrowLedgerEntry, FinancialAudit, RentalEvidence):
    event.listen(model, "before_delete", immutable)
    if model is not JournalTransaction:
        event.listen(model, "before_update", immutable)


@event.listens_for(RefundIntent, "before_update")
def immutable_refund_allocation(mapper, connection, target):
    fields = ("booking_id", "amount_paise", "deduction_paise", "kind", "authorized_by")
    if any(inspect(target).attrs[name].history.has_changes() for name in fields):
        raise ValueError("Refund allocation is immutable")


@event.listens_for(RentalBooking, "before_update")
def immutable_snapshot(mapper, connection, target):
    fields = (
        "borrow_request_id",
        "offer_id",
        "listing_id",
        "borrower_id",
        "lender_id",
        "start_date",
        "end_date",
        "duration_days",
        "daily_rate_paise",
        "rental_fee_paise",
        "security_deposit_paise",
        "total_amount_paise",
        "currency",
        "provider",
    )
    if any(inspect(target).attrs[name].history.has_changes() for name in fields):
        raise ValueError("Booking price/identity snapshots are immutable")
