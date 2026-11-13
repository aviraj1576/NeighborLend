"""Append-only balanced journal; settlement authorization belongs to the application."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import select

from app.payment_models import EscrowLedgerEntry, JournalTransaction


def paise(value):
    if isinstance(value, bool):
        raise ValueError("Invalid currency value")
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > Decimal("10000000"):
            raise ValueError("Invalid currency value")
        return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Invalid currency value") from exc


def balanced_lines(lines):
    if not lines or any(
        type(amount) is not int or amount <= 0 or side not in {"DEBIT", "CREDIT"}
        for _, side, amount in lines
    ):
        raise ValueError("Positive integer journal lines required")
    debit = sum(amount for _, side, amount in lines if side == "DEBIT")
    credit = sum(amount for _, side, amount in lines if side == "CREDIT")
    if debit != credit or not debit:
        raise ValueError("Unbalanced financial journal")
    return debit


def post(db, booking, reference, lines, description):
    lines = [line for line in lines if line[2] != 0]
    total = balanced_lines(lines)
    existing = db.scalar(
        select(JournalTransaction).where(JournalTransaction.reference == reference)
    )
    if existing:
        stored = db.scalars(
            select(EscrowLedgerEntry).where(EscrowLedgerEntry.journal_id == existing.id)
        ).all()
        if (
            existing.booking_id != booking.id
            or existing.status != "posted"
            or existing.debit_paise != total
            or existing.credit_paise != total
            or sorted((row.account_type, row.entry_type, row.amount_paise) for row in stored)
            != sorted(lines)
        ):
            raise ValueError("Journal idempotency reference conflicts with its immutable posting")
        return existing
    journal = JournalTransaction(
        booking_id=booking.id,
        reference=reference,
        debit_paise=total,
        credit_paise=total,
        status="draft",
    )
    db.add(journal)
    db.flush()
    for account, side, amount in lines:
        db.add(
            EscrowLedgerEntry(
                journal_id=journal.id,
                booking_id=booking.id,
                account_type=account,
                entry_type=side,
                amount_paise=amount,
                description=description,
            )
        )
    db.flush()
    journal.status = "posted"
    db.flush()
    return journal
