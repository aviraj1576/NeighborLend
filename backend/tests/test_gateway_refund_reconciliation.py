"""Real API/service/adapter boundaries; isolated database and synthetic transport only."""

import hashlib
import hmac
import json

import pytest
from sqlalchemy import func, select
from test_razorpay_escrow import assert_balanced, call
from test_refund_workflow_debugging import authorize_clean_return
from test_refund_workflow_debugging import flow as payment_flow

from app.payment_models import FinancialAudit, JournalTransaction, ProcessedWebhook, RefundIntent
from app.services.razorpay_service import ProviderError

flow = payment_flow


def gateway(flow):
    provider = authorize_clean_return(flow)
    del provider.refund_snapshot  # Exercise the actual GET-only adapter implementation.
    refunds, requests = [], []
    state = {"unavailable": False, "currency": "INR"}

    def transport(method, path, data, headers):
        requests.append((method, path))
        if state["unavailable"]:
            raise ProviderError("provider_outcome_unknown")
        if (method, path) == ("GET", "payments/pay_fixture"):
            amount = sum(r["amount"] for r in refunds if r["status"] != "failed")
            return dict(
                id="pay_fixture",
                order_id="order_fixture",
                amount=58000,
                currency=state["currency"],
                captured=True,
                amount_refunded=amount,
                status="refunded" if amount == 58000 else "captured",
            )
        if method == "GET" and path.startswith("payments/pay_fixture/refunds?"):
            return {"items": [dict(r) for r in refunds]}
        if method == "GET" and path.startswith("refunds/"):
            return dict(next(r for r in refunds if r["id"] == path.split("/")[1]))
        if (method, path) == ("POST", "payments/pay_fixture/refund"):
            assert data["amount"] == 40000, "Clean return must preserve all 18000 rental paise"
            assert headers["X-Refund-Idempotency"] == data["receipt"]
            refund = dict(
                id="rfnd_deposit",
                payment_id="pay_fixture",
                amount=data["amount"],
                currency="INR",
                receipt=data["receipt"],
                status="processed",
            )
            refunds.append(refund)
            return dict(refund)
        raise AssertionError("Unexpected synthetic gateway operation")

    provider.transport = transport
    return refunds, requests, state, provider


def inspect(flow, role="borrower"):
    return flow["client"].get(
        f"/api/payments/bookings/{flow['booking']['id']}/gateway-reconciliation",
        headers=flow["headers"][role],
    )


def external(refunds, *, amount=18000, status="processed", receipt=None):
    refunds.append(
        dict(
            id="rfnd_external",
            payment_id="pay_fixture",
            amount=amount,
            currency="INR",
            status=status,
            receipt=receipt,
            notes={"comment": ""},
        )
    )


@pytest.mark.parametrize("flow", ["refund_incident"], indirect=True)
def test_exact_drill_clean_return_retains_rent_and_detects_external_refund(flow):
    refunds, requests, _, _ = gateway(flow)
    settled = call(flow, "payments/refunds/execute", {"gateway_refund_approved": True})
    assert settled.status_code == 200, settled.text
    data = settled.json()
    assert (
        data["total_amount_paise"],
        data["security_deposit_paise"],
        data["rental_fee_paise"],
    ) == (58000, 40000, 18000)
    assert data["deposit_refunded_paise"] == 40000
    assert data["lender_settlement"]["rental_earnings_payable_paise"] == 18000
    assert inspect(flow).json()["status"] == "verified"
    external(refunds)
    result = inspect(flow)
    assert result.status_code == 200
    assert result.json()["status"] == "review_required"
    assert result.json()["amount_refunded_paise"] == 58000
    assert result.json()["remaining_gross_paise"] == 0
    assert "refund_exceeds_authorized_allocation" in result.json()["issues"]
    # GET remains read-only; recording verified review is explicit and administrator-only.
    with flow["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(JournalTransaction)) == 2
        assert (
            db.scalar(
                select(FinancialAudit).where(
                    FinancialAudit.action == "gateway_refund_review_required"
                )
            )
            is None
        )
    for role in ("borrower", "lender", "other"):
        assert call(flow, "payments/refunds/inspect", role=role).status_code == 403
    reconciled = call(flow, "payments/refunds/reconcile", role="admin")
    assert (
        reconciled.status_code == 200
        and reconciled.json()["gateway_reconciliation"]["status"] == "review_required"
    )
    for _ in range(2):
        recorded = call(flow, "payments/refunds/inspect", role="admin")
        assert recorded.status_code == 200 and recorded.json()["gateway_review"]
    queue = flow["client"].get("/api/disputes", headers=flow["headers"]["admin"]).json()
    assert queue[0]["gateway_review"] is True
    assert (
        call(flow, "payments/refunds/execute", {"gateway_refund_approved": True}).status_code == 409
    )
    assert len([r for r in requests if r[0] == "POST"]) == 1
    with flow["factory"]() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(FinancialAudit)
                .where(FinancialAudit.action == "gateway_refund_review_required")
            )
            == 1
        )
        assert db.scalar(select(RefundIntent)).amount_paise == 40000
        assert db.scalar(select(func.count()).select_from(JournalTransaction)) == 2
    assert_balanced(flow)


@pytest.mark.parametrize("flow", ["refund_incident"], indirect=True)
@pytest.mark.parametrize("failure", ["external", "unavailable", "currency"])
def test_new_dispatch_fails_closed_when_gateway_cannot_support_it(flow, failure):
    refunds, requests, state, _ = gateway(flow)
    if failure == "external":
        external(refunds, amount=40000)
    elif failure == "unavailable":
        state["unavailable"] = True
    else:
        state["currency"] = "USD"
    result = call(flow, "payments/refunds/execute", {"gateway_refund_approved": True})
    assert result.status_code == (409 if failure == "external" else 503)
    assert not any(r[0] == "POST" for r in requests)
    with flow["factory"]() as db:
        assert db.scalar(select(RefundIntent)).status == "created"
        assert db.scalar(select(func.count()).select_from(JournalTransaction)) == 1


@pytest.mark.parametrize("flow", ["refund_incident"], indirect=True)
@pytest.mark.parametrize("status", ["pending", "processed", "failed"])
def test_lost_post_is_recovered_by_receipt_without_new_post(flow, status):
    refunds, requests, _, _ = gateway(flow)
    with flow["factory"]() as db:
        intent = db.scalar(select(RefundIntent))
        key = intent.idempotency_key
    external(refunds, amount=40000, receipt=key, status=status)
    result = call(flow, "payments/refunds/execute", {"gateway_refund_approved": True})
    assert result.status_code == 200 and result.json()["refund"]["status"] == status
    assert not any(r[0] == "POST" for r in requests)
    assert_balanced(flow)


@pytest.mark.parametrize("flow", ["refund_incident"], indirect=True)
def test_concurrent_admin_review_deduplicates_without_ledger_changes(flow):
    from concurrent.futures import ThreadPoolExecutor

    refunds, requests, _, _ = gateway(flow)
    external(refunds)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: call(flow, "payments/refunds/inspect", role="admin"), range(2))
        )
    assert all(r.status_code == 200 for r in results)
    with flow["factory"]() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(FinancialAudit)
                .where(FinancialAudit.action == "gateway_refund_review_required")
            )
            == 1
        )
        assert db.scalar(select(func.count()).select_from(JournalTransaction)) == 1
    assert not any(r[0] == "POST" for r in requests)


@pytest.mark.parametrize("flow", ["refund_incident"], indirect=True)
def test_malformed_refund_response_fails_closed_and_incomplete_pages_are_rejected(flow):
    _, requests, _, provider = gateway(flow)
    original = provider.transport

    def malformed(method, path, data, headers):
        if path.startswith("payments/pay_fixture/refunds?"):
            return {
                "items": [
                    dict(
                        id="rfnd_bad",
                        payment_id="pay_fixture",
                        amount=40000,
                        currency="INR",
                        status={},
                    )
                ]
            }
        return original(method, path, data, headers)

    provider.transport = malformed
    assert inspect(flow).json()["status"] == "unavailable"

    def endless(method, path, data, headers):
        if path.startswith("payments/pay_fixture/refunds?"):
            return {"items": [{} for _ in range(100)]}
        return original(method, path, data, headers)

    provider.transport = endless
    result = inspect(flow).json()
    assert (
        result["status"] == "unavailable" and result["error_code"] == "refund_inventory_incomplete"
    )
    assert not any(r[0] == "POST" for r in requests)


@pytest.mark.parametrize("flow", ["refund_incident"], indirect=True)
@pytest.mark.parametrize("status", ["pending", "processed", "failed"])
@pytest.mark.parametrize("kind", ["refund.created", "refund.processed"])
def test_external_webhook_records_review_without_settlement_or_refund(flow, status, kind):
    refunds, requests, _, _ = gateway(flow)
    external(refunds, status=status)
    raw = json.dumps(
        {"event": kind, "payload": {"refund": {"entity": {"id": "rfnd_external"}}}}
    ).encode()
    headers = {
        "x-razorpay-event-id": "external_event",
        "x-razorpay-signature": hmac.new(b"fixture-webhook", raw, hashlib.sha256).hexdigest(),
    }
    for _ in range(2):
        result = flow["client"].post("/api/payments/webhook", content=raw, headers=headers)
        assert result.status_code == 200, result.text
    assert not any(r[0] == "POST" for r in requests)
    with flow["factory"]() as db:
        assert db.get(ProcessedWebhook, "external_event").status == "processed"
        assert db.scalar(select(RefundIntent)).status == "created"
        assert db.scalar(select(func.count()).select_from(JournalTransaction)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(FinancialAudit)
                .where(FinancialAudit.action == "gateway_refund_review_required")
            )
            == 1
        )


@pytest.mark.parametrize("flow", ["refund_incident"], indirect=True)
def test_gateway_read_authorization_and_provider_failure_are_explicit(flow):
    _, _, state, _ = gateway(flow)
    assert inspect(flow, "other").status_code == 403
    assert inspect(flow, "admin").status_code == 200
    state["unavailable"] = True
    assert inspect(flow).json()["status"] == "unavailable"
