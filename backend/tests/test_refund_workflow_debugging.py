"""Refund regression coverage using isolated databases and a synthetic gateway transport."""

import pytest
from sqlalchemy import func, select
from test_razorpay_escrow import (
    assert_balanced,
    call,
    physical_return,
    razorpay_flow,
)
from test_razorpay_escrow import flow as payment_flow

from app.main import app
from app.payment_models import FinancialAudit, RefundAttempt, RefundIntent
from app.routers.payments import payment_provider
from app.services.payments import PaymentService

flow = payment_flow


@pytest.mark.parametrize("flow", ["razorpay_test"], indirect=True)
def test_refund_operations_are_admin_only_even_for_participants(flow):
    provider = authorize_clean_return(flow)

    def forbidden_transport(*args):
        pytest.fail("Non-admin refund operations must not reach the provider")

    provider.transport = forbidden_transport
    for role in ("borrower", "lender", "other"):
        for endpoint, payload in (
            ("payments/refunds/execute", {"gateway_refund_approved": True}),
            ("payments/refunds/execute", {"gateway_refund_approved": True, "retry_failed": True}),
            ("payments/refunds/reconcile", {}),
        ):
            assert call(flow, endpoint, payload, role=role).status_code == 403
    # The compatibility endpoint may authorize the lender's already confirmed
    # clean return, but cannot dispatch or reconcile the refund.
    legacy = call(flow, "payments/refund-deposit", role="lender")
    assert legacy.status_code == 200 and legacy.json()["refund"]["status"] == "created"
    with flow["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(RefundAttempt)) == 0
        assert db.scalar(select(RefundIntent)).status == "created"
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as denied:
            PaymentService(db, provider).execute_refund(
                flow["booking"]["id"], flow["ids"]["borrower"], admin=True
            )
        assert denied.value.status_code == 403


def authorize_clean_return(flow):
    _, signature = razorpay_flow(flow)
    assert call(flow, "payments/create-order").status_code == 200
    assert call(
        flow,
        "payments/verify",
        {"order_id": "order_fixture", "payment_id": "pay_fixture", "signature": signature},
    ).status_code == 200
    physical_return(flow)
    response = flow["client"].post(
        f"/api/borrow-requests/{flow['request_id']}/return/confirm",
        headers=flow["headers"]["lender"],
        json={"approved": True, "condition_note": "Synthetic clean return"},
    )
    assert response.status_code == 200, response.text
    return app.dependency_overrides[payment_provider]()


@pytest.mark.parametrize("flow", ["razorpay_test"], indirect=True)
def test_reconcile_unsent_intent_preserves_authorization_without_dispatch_attempt(flow):
    provider = authorize_clean_return(flow)
    requests = []

    def transport(method, path, data, headers):
        requests.append((method, path))
        assert method == "GET", "Reconciliation must never dispatch a refund"
        if path.startswith("payments/pay_fixture/refunds?"):
            return {"items": []}
        raise AssertionError(path)

    provider.transport = transport
    for _ in range(2):
        response = call(flow, "payments/refunds/reconcile")
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["refund"]["status"] == "created"
        assert result["refund"]["amount_paise"] == 50000
        assert result["deposit_refunded_paise"] == 0
        assert result["booking_status"] == "settling"
        assert result["reconciliation"]["balanced"] is True
    assert requests == []
    with flow["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(RefundAttempt)) == 0
        assert db.scalar(select(RefundIntent)).error_code is None
    assert_balanced(flow)


@pytest.mark.parametrize("flow", ["razorpay_test"], indirect=True)
def test_unsent_refund_still_requires_approval_and_rental_authorization(flow):
    provider = authorize_clean_return(flow)

    def forbidden_transport(*args):
        pytest.fail("Rejected authorization must not reach the provider")

    provider.transport = forbidden_transport
    assert call(flow, "payments/refunds/execute").status_code == 403
    assert call(
        flow, "payments/refunds/execute", {"gateway_refund_approved": True}, role="other"
    ).status_code == 403
    assert call(flow, "payments/refunds/reconcile", role="other").status_code == 403
    with flow["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(RefundAttempt)) == 0
        assert db.scalar(select(RefundIntent)).status == "created"


@pytest.mark.parametrize("flow", ["razorpay_test"], indirect=True)
def test_admin_queue_exposes_authorized_refund_without_dispatching(flow):
    provider = authorize_clean_return(flow)

    def forbidden_transport(*args):
        pytest.fail("Reading the review queue must never contact the gateway")

    provider.transport = forbidden_transport
    client = flow["client"]
    for role in ("borrower", "lender", "other"):
        assert client.get("/api/disputes", headers=flow["headers"][role]).status_code == 403
    response = client.get("/api/disputes", headers=flow["headers"]["admin"])
    assert response.status_code == 200
    row = next(row for row in response.json() if row["booking_id"] == flow["booking"]["id"])
    assert row["refund"]["status"] == "created"
    assert row["refund"]["amount_paise"] == 50000
    assert row["borrower_id"] == flow["ids"]["borrower"]
    assert row["lender_id"] == flow["ids"]["lender"]
    with flow["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(RefundAttempt)) == 0
    requests = []

    def synthetic_refund(method, path, data, headers):
        requests.append((method, path))
        assert (method, path) == ("POST", "payments/pay_fixture/refund")
        assert data["amount"] == 50000
        return {
            "id": "rfnd_synthetic", "payment_id": "pay_fixture", "amount": data["amount"],
            "currency": "INR", "receipt": data["receipt"], "status": "processed",
        }

    provider.transport = synthetic_refund
    # The actual admin execute handler is exercised against synthetic transport.
    assert call(flow, "payments/refunds/execute", role="admin").status_code == 403
    for _ in range(2):
        result = call(flow, "payments/refunds/execute", {"gateway_refund_approved": True}, role="admin")
        assert result.status_code == 200, result.text
        assert result.json()["refund"]["status"] == "processed"
        assert result.json()["deposit_refunded_paise"] == 50000
        assert result.json()["deduction_paise"] == 0
    assert requests == [("POST", "payments/pay_fixture/refund")]
    assert_balanced(flow)
    # A completed refund must leave the actionable review queue.
    assert client.get("/api/disputes", headers=flow["headers"]["admin"]).json() == []


@pytest.mark.parametrize("flow", ["razorpay_test"], indirect=True)
def test_pending_refund_checks_are_get_only_and_only_confirmed_processing_posts_settlement(flow):
    provider = authorize_clean_return(flow)
    requests = []
    saved = {}

    def transport(method, path, data, headers):
        requests.append((method, path))
        if method == "POST" and path == "payments/pay_fixture/refund":
            saved.update(id="rfnd_pendingfixture", payment_id="pay_fixture", amount=data["amount"],
                         currency="INR", receipt=data["receipt"], status="pending")
        else:
            assert (method, path) == ("GET", "refunds/rfnd_pendingfixture")
        return dict(saved)

    provider.transport = transport
    first = call(flow, "payments/refunds/execute", {"gateway_refund_approved": True})
    assert first.status_code == 200 and first.json()["refund"]["status"] == "pending"
    pending = call(flow, "payments/refunds/reconcile")
    assert pending.status_code == 200
    assert pending.json()["refund"]["status"] == "pending"
    assert pending.json()["deposit_refunded_paise"] == 0
    assert pending.json()["held_deposit_paise"] == 50000
    saved["status"] = "processed"  # Synthetic transport only; never the actual gateway.
    for _ in range(2):
        final = call(flow, "payments/refunds/reconcile")
        assert final.status_code == 200 and final.json()["deposit_refunded_paise"] == 50000
    assert requests == [("POST", "payments/pay_fixture/refund"),
                        ("GET", "refunds/rfnd_pendingfixture"), ("GET", "refunds/rfnd_pendingfixture")]
    with flow["factory"]() as db:
        actions = db.scalars(select(FinancialAudit.action)).all()
        assert actions.count("refund_requested") == 1
        assert actions.count("refund_status_check_requested") == 2
    assert_balanced(flow)
