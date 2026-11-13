"""Real PostgreSQL financial constraints, browser-role denial and concurrency."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from test_razorpay_escrow import assert_balanced, call, fund, physical_return
from test_razorpay_escrow import flow as payment_flow

from app.payment_models import JournalTransaction, RefundIntent
from app.services.payments import PaymentService

flow = payment_flow
pytestmark = pytest.mark.parametrize("flow", ["postgres"], indirect=True)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE rental_bookings SET total_amount_paise=1",
        "UPDATE rental_bookings SET borrower_id='missing-user'",
        "UPDATE payment_transactions SET amount_paise=1",
        "UPDATE payment_transactions SET currency='USD'",
        "DELETE FROM payment_transactions",
    ],
)
def test_postgres_rejects_financial_tampering(flow, statement):
    call(flow, "payments/create-order")
    with flow["factory"]() as db:
        with pytest.raises(DBAPIError):
            db.execute(text(statement))
            db.commit()
        db.rollback()


def test_postgres_prevents_duplicate_capture_and_wrong_order(flow):
    fund(flow)
    with flow["factory"]() as db:
        with pytest.raises(DBAPIError):
            db.execute(
                text("""INSERT INTO payment_transactions
                (id,booking_id,provider,transaction_type,amount_paise,currency,status,idempotency_key,
                 razorpay_order_id,razorpay_payment_id,operation_version,created_at)
                SELECT :id,booking_id,provider,transaction_type,amount_paise,currency,status,:key,
                 razorpay_order_id,:payment,operation_version,created_at FROM payment_transactions
                WHERE transaction_type='payment' AND status='captured'"""),
                {"id": str(uuid4()), "key": str(uuid4()), "payment": "pay_duplicate"},
            )
            db.commit()
        db.rollback()
        with pytest.raises(DBAPIError):
            db.execute(
                text(
                    "UPDATE payment_transactions SET razorpay_order_id='order_wrong' WHERE transaction_type='payment'"
                )
            )
            db.commit()
        db.rollback()
    assert_balanced(flow)


def test_postgres_rejects_excess_refund_and_posted_journal_mutations(flow):
    fund(flow)
    physical_return(flow)
    with flow["factory"]() as db:
        service = PaymentService(db, flow["provider"])
        service.return_decision(flow["booking"]["id"], flow["ids"]["lender"], True)
    for statement in [
        "UPDATE refund_intents SET amount_paise=amount_paise+1",
        "DELETE FROM refund_intents",
        "UPDATE journal_transactions SET status='draft'",
        "DELETE FROM escrow_ledger_entries",
        "UPDATE escrow_ledger_entries SET amount_paise=1",
    ]:
        with flow["factory"]() as db:
            with pytest.raises(DBAPIError):
                db.execute(text(statement))
                db.commit()
            db.rollback()
    assert_balanced(flow)


def test_postgres_browser_roles_have_no_financial_access(flow):
    with flow["factory"]() as db:
        schema = db.execute(text("SELECT current_schema()")).scalar()
        # Grant schema visibility in this UUID schema to test table denial itself.
        db.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO anon,authenticated'))
        db.commit()
        for role in ("anon", "authenticated"):
            functions = (
                db.execute(
                    text("""SELECT p.oid FROM pg_proc p
                JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname=current_schema() AND left(p.proname,3)='nl_'""")
                )
                .scalars()
                .all()
            )
            for function in functions:
                assert not db.execute(
                    text("SELECT has_function_privilege(:role,:function,'EXECUTE')"),
                    {"role": role, "function": function},
                ).scalar()
            for table in (
                "rental_bookings",
                "payment_transactions",
                "refund_intents",
                "financial_audit_records",
            ):
                db.execute(text(f"SET LOCAL ROLE {role}"))
                with pytest.raises(DBAPIError):
                    db.execute(text(f'SELECT * FROM "{schema}".{table}'))
                db.rollback()


def test_postgres_return_and_claim_race_commits_one_decision(flow):
    fund(flow)
    physical_return(flow)
    barrier = Barrier(2)

    def decide(claim):
        with flow["factory"]() as db:
            service = PaymentService(db, flow["provider"])
            barrier.wait(timeout=10)
            try:
                if claim:
                    service.claim(
                        flow["booking"]["id"],
                        flow["ids"]["lender"],
                        10000,
                        "Synthetic condition claim",
                    )
                else:
                    service.return_decision(flow["booking"]["id"], flow["ids"]["lender"], True)
                return "committed"
            except HTTPException as exc:
                assert exc.status_code == 409
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, [False, True]))
    assert sorted(results) == ["committed", "conflict"]
    assert_balanced(flow)


def test_postgres_concurrent_refund_settles_once(flow):
    fund(flow)
    physical_return(flow)
    with flow["factory"]() as db:
        PaymentService(db, flow["provider"]).return_decision(
            flow["booking"]["id"], flow["ids"]["lender"], True
        )
    barrier = Barrier(2)

    def settle(_):
        with flow["factory"]() as db:
            barrier.wait(timeout=10)
            try:
                return PaymentService(db, flow["provider"]).reconcile_refund(
                    flow["booking"]["id"], flow["ids"]["admin"], admin=True
                )
            except HTTPException as exc:
                assert exc.status_code == 409
                return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(settle, range(2)))
    assert any(row and row["booking_status"] == "completed" for row in results)
    with flow["factory"]() as db:
        assert db.scalar(select(RefundIntent)).status == "processed"
        assert (
            len(
                db.scalars(
                    select(JournalTransaction).where(
                        JournalTransaction.reference.like("settlement:%")
                    )
                ).all()
            )
            == 1
        )
    assert_balanced(flow)
