"""Optional real PostgreSQL integration; never uses the application's DATABASE_URL."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select
from test_razorpay_escrow import assert_balanced, call, fund, physical_return
from test_razorpay_escrow import flow as payment_flow

from app.payment_models import JournalTransaction
from app.services.payments import PaymentService

flow = payment_flow


@pytest.mark.parametrize("flow", ["postgres"], indirect=True)
def test_postgres_migrations_locks_and_concurrent_capture(flow):
    assert call(flow, "payments/create-order").status_code == 200

    def capture(_):
        with flow["factory"]() as db:
            return PaymentService(db, flow["provider"]).demo_pay(
                flow["booking"]["id"], flow["ids"]["borrower"], "success"
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(row["payment_status"] == "captured" for row in pool.map(capture, range(2)))
    with flow["factory"]() as db:
        assert len(db.scalars(select(JournalTransaction)).all()) == 1
    assert_balanced(flow)


@pytest.mark.parametrize("flow", ["postgres"], indirect=True)
def test_postgres_clean_return_and_journal(flow):
    fund(flow)
    physical_return(flow)
    result = flow["client"].post(
        f"/api/borrow-requests/{flow['request_id']}/return/confirm",
        json={"approved": True},
        headers=flow["headers"]["lender"],
    )
    assert result.status_code == 200, result.text
    assert call(flow, "payments/refunds/reconcile").json()["deposit_refunded_paise"] == 50000
    assert_balanced(flow)


@pytest.mark.parametrize("flow", ["postgres"], indirect=True)
def test_postgres_rejection_admin_resolution_and_refund(flow):
    fund(flow)
    physical_return(flow)
    assert (
        call(
            flow,
            "disputes/raise",
            {"claimed_deduction_paise": 20000, "reason": "Review damage"},
            "lender",
        ).status_code
        == 200
    )
    assert call(flow, "disputes/respond", {"accepted": False}).status_code == 200
    assert (
        call(
            flow,
            "disputes/settle",
            {"approved_deduction_paise": 10000, "reason": "Reviewed evidence"},
            "admin",
        ).status_code
        == 200
    )
    assert call(flow, "payments/refunds/reconcile").json()["deposit_refunded_paise"] == 40000
    assert_balanced(flow)
