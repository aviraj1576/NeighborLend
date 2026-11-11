"""Lifecycle acceptance and refund recovery; all mutations use disposable databases."""

import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from test_razorpay_escrow import (
    assert_balanced,
    call,
    evidence,
    fund,
    physical_return,
    razorpay_flow,
)
from test_razorpay_escrow import flow as payment_flow

from app.main import app
from app.payment_models import JournalTransaction, RefundAttempt, RefundIntent
from app.routers.payments import payment_provider
from app.services.payments import PaymentService
from app.services.razorpay_service import ProviderError

flow = payment_flow


def view(flow):
    return (
        flow["client"]
        .get("/api/payments/bookings/" + flow["booking"]["id"], headers=flow["headers"]["borrower"])
        .json()
    )


def review(flow, deduction):
    assert (
        call(
            flow,
            "disputes/raise",
            {
                "claimed_deduction_paise": deduction,
                "reason": "Simulated casing damage shown by return evidence",
            },
            "lender",
        ).status_code
        == 200
    )
    assert (
        call(
            flow,
            "disputes/settle",
            {
                "approved_deduction_paise": deduction,
                "reason": "Independent human review of return evidence",
            },
            "admin",
        ).status_code
        == 200
    )


@pytest.mark.parametrize("flow", ["realistic"], indirect=True)
@pytest.mark.parametrize(
    "deduction,refund,allocation", [(0, 200000, 50000), (60000, 140000, 110000)]
)
def test_realistic_full_and_partial_deposit_lifecycle(flow, deduction, refund, allocation):
    order = call(flow, "payments/create-order").json()
    assert order["amount_paise"] == 250000
    funded = call(flow, "payments/mock-confirm").json()
    assert funded["rental_fee_paise"] == 50000
    assert funded["security_deposit_paise"] == 200000
    assert funded["handover_unlocked"]
    assert call(flow, "payments/refund-deposit", role="lender").status_code == 409
    physical_return(flow)
    if deduction:
        review(flow, deduction)
    else:
        response = flow["client"].post(
            "/api/borrow-requests/" + flow["request_id"] + "/return/confirm",
            json={"approved": True},
            headers=flow["headers"]["lender"],
        )
        assert response.status_code == 200, response.text
    with ThreadPoolExecutor(max_workers=2) as executor:

        def settle(_):
            with flow["factory"]() as db:
                try:
                    return PaymentService(db, flow["provider"]).reconcile_refund(
                        flow["booking"]["id"], flow["ids"]["borrower"]
                    )
                except HTTPException as exc:
                    assert (
                        exc.status_code == 409
                    )  # A live dispatch is fenced; reconcile afterwards.
                    return None

        results = list(executor.map(settle, range(2)))
    assert any(row and row["deposit_refunded_paise"] == refund for row in results)
    assert all(row is None or row["deposit_refunded_paise"] == refund for row in results)
    result = view(flow)
    assert result["deduction_paise"] == deduction
    assert result["held_deposit_paise"] == 0
    assert not result["handover_unlocked"]
    assert (
        sum(
            row["amount_paise"]
            for row in result["journal"]
            if row["account"] == "lender_receivable_simulated"
        )
        == allocation
    )
    assert (
        sum(
            row["amount_paise"]
            for row in result["journal"]
            if row["account"] == "gateway_clearing" and row["side"] == "CREDIT"
        )
        == refund
    )
    with flow["factory"]() as db:
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


def test_participants_cannot_approve_even_with_borrower_consent_or_admin_role(flow):
    fund(flow)
    physical_return(flow)
    assert (
        call(
            flow,
            "disputes/raise",
            {"claimed_deduction_paise": 20000, "reason": "Human claim"},
            "lender",
        ).status_code
        == 200
    )
    assert call(flow, "disputes/respond", {"accepted": True}).status_code == 200
    for role in ["lender", "borrower"]:
        assert (
            call(
                flow,
                "disputes/settle",
                {"approved_deduction_paise": 20000, "reason": "Self approval"},
                role,
            ).status_code
            == 403
        )
        with flow["factory"]() as db, pytest.raises(Exception) as failure:
            PaymentService(db, flow["provider"]).resolve(
                flow["booking"]["id"],
                flow["ids"][role],
                20000,
                admin=True,
                reason="Participant cannot be reviewer",
            )
        assert failure.value.status_code == 403
    assert view(flow)["refund"] is None


def test_platform_cannot_refund_dispute_before_return(flow):
    fund(flow)
    assert (
        flow["client"]
        .post(
            "/api/borrow-requests/" + flow["request_id"] + "/dispute",
            json={"description": "Human review requested before receipt"},
            headers=flow["headers"]["borrower"],
        )
        .status_code
        == 200
    )
    result = call(
        flow, "disputes/settle", {"approved_deduction_paise": 0, "reason": "No return yet"}, "admin"
    )
    assert result.status_code == 409
    assert view(flow)["refund"] is None


def test_early_dispute_can_use_existing_pre_receipt_full_refund_policy(flow):
    fund(flow)
    assert (
        flow["client"]
        .post(
            "/api/borrow-requests/" + flow["request_id"] + "/dispute",
            json={"description": "No item received; platform recovery requested"},
            headers=flow["headers"]["borrower"],
        )
        .status_code
        == 200
    )
    payload = {
        "action": "cancel",
        "reason": "Independent reviewer confirms item stayed with lender; pre-receipt cancellation",
    }
    assert call(flow, "disputes/handover-issue/resolve", payload, "lender").status_code == 403
    result = call(flow, "disputes/handover-issue/resolve", payload, "admin")
    assert result.status_code == 200, result.text
    assert result.json()["refund"]["amount_paise"] == 90000
    result = call(flow, "payments/refunds/reconcile").json()
    assert result["booking_status"] == "cancelled"
    assert result["deduction_paise"] == 0 and result["held_deposit_paise"] == 0
    assert not result["handover_unlocked"]
    for account in [
        "escrow_deposit_held",
        "escrow_deposit_frozen",
        "rental_fee_clearing",
        "gateway_clearing",
    ]:
        assert (
            sum(
                (1 if row["side"] == "DEBIT" else -1) * row["amount_paise"]
                for row in result["journal"]
                if row["account"] == account
            )
            == 0
        )
    assert_balanced(flow)


def test_received_dispute_requires_return_and_admin_can_unblock_return_evidence(flow):
    fund(flow)
    path = "/api/borrow-requests/" + flow["request_id"]
    photo = evidence(flow, "handover", "lender")
    assert (
        flow["client"]
        .post(
            path + "/handover/upload-photos",
            json={"photo_urls": [photo]},
            headers=flow["headers"]["lender"],
        )
        .status_code
        == 200
    )
    assert (
        flow["client"]
        .post(path + "/handover/borrower-confirm", json={}, headers=flow["headers"]["borrower"])
        .status_code
        == 200
    )
    assert (
        flow["client"]
        .post(
            path + "/dispute",
            json={"description": "Received item condition issue"},
            headers=flow["headers"]["borrower"],
        )
        .status_code
        == 200
    )
    assert (
        call(
            flow,
            "disputes/handover-issue/resolve",
            {"action": "cancel", "reason": "Received item cannot use pre-receipt cancellation"},
            "admin",
        ).status_code
        == 409
    )
    assert (
        call(
            flow,
            "disputes/handover-issue/resolve",
            {
                "action": "return",
                "reason": "Human reviewer confirms item is held by borrower; arrange return",
            },
            "admin",
        ).status_code
        == 200
    )
    photo = evidence(flow, "return", "borrower")
    assert (
        flow["client"]
        .post(
            path + "/return/upload-photos",
            json={"photo_urls": [photo]},
            headers=flow["headers"]["borrower"],
        )
        .status_code
        == 200
    )
    assert (
        call(
            flow,
            "disputes/settle",
            {
                "approved_deduction_paise": 0,
                "reason": "Independent review dismisses claim after physical return",
            },
            "admin",
        ).status_code
        == 200
    )
    assert call(flow, "payments/refunds/reconcile").json()["deposit_refunded_paise"] == 50000
    assert_balanced(flow)


def gateway_return(flow):
    _, signature = razorpay_flow(flow)
    assert call(flow, "payments/create-order").status_code == 200
    assert (
        call(
            flow,
            "payments/verify",
            {"order_id": "order_fixture", "payment_id": "pay_fixture", "signature": signature},
        ).status_code
        == 200
    )
    physical_return(flow)
    provider = app.dependency_overrides[payment_provider]()
    original, calls, refund = provider.transport, [], {}

    def transport(method, path, data, headers):
        calls.append((method, path))
        if path == "payments/pay_fixture/refund":
            refund.update(
                id="rfnd_final",
                payment_id="pay_fixture",
                amount=50000,
                currency="INR",
                status="pending",
                receipt=data["receipt"],
            )
            return dict(refund)
        if path.startswith("payments/pay_fixture/refunds?"):
            return {"items": [dict(refund)] if refund else []}
        if path == "refunds/rfnd_final":
            return dict(refund)
        return original(method, path, data, headers)

    provider.transport = transport
    response = flow["client"].post(
        "/api/borrow-requests/" + flow["request_id"] + "/return/confirm",
        json={"approved": True},
        headers=flow["headers"]["lender"],
    )
    assert response.status_code == 200, response.text
    assert calls == []  # Return approval never dispatches a gateway refund.
    return provider, calls, refund


@pytest.mark.parametrize("flow", ["razorpay_test"], indirect=True)
def test_refund_approval_is_explicit_and_reconciliation_never_dispatches(flow):
    _, calls, _ = gateway_return(flow)
    assert call(flow, "payments/refunds/execute").status_code == 403
    assert (
        call(
            flow,
            "payments/refunds/reconcile",
            {"retry_failed": True, "gateway_refund_approved": True},
            "admin",
        ).status_code
        == 403
    )
    assert (
        call(flow, "payments/refunds/execute", {"gateway_refund_approved": "true"}).status_code
        == 422
    )
    assert call(flow, "payments/refunds/reconcile").status_code == 503
    assert all(method == "GET" for method, _ in calls)
    assert (
        call(
            flow, "payments/refunds/execute", {"gateway_refund_approved": True}, "other"
        ).status_code
        == 403
    )
    result = call(flow, "payments/refunds/execute", {"gateway_refund_approved": True})
    assert result.status_code == 200, result.text
    assert result.json()["refund"]["status"] == "pending"
    assert result.json()["deposit_refunded_paise"] == 0
    assert sum(method == "POST" for method, _ in calls) == 1


@pytest.mark.parametrize("flow", ["razorpay_test"], indirect=True)
@pytest.mark.parametrize("mismatch", ["id", "receipt", "currency", "amount", "payment_id"])
def test_gateway_refund_response_mismatch_cannot_post_settlement(flow, mismatch):
    provider, _, _ = gateway_return(flow)
    original = provider.transport

    def wrong(method, path, data, headers):
        result = original(method, path, data, headers)
        if method == "POST":
            result["status"] = "processed"
            result[mismatch] = {
                "id": "pay_wrong",
                "receipt": "unrelated",
                "currency": "USD",
                "amount": 50001,
                "payment_id": "pay_other",
            }[mismatch]
        return result

    provider.transport = wrong
    assert (
        call(flow, "payments/refunds/execute", {"gateway_refund_approved": True}).status_code == 503
    )
    result = view(flow)
    assert result["refund"]["status"] == "unknown"
    assert result["deposit_refunded_paise"] == 0
    assert result["held_deposit_paise"] == 50000
    assert len({row["journal_id"] for row in result["journal"]}) == 1


@pytest.mark.parametrize("flow", ["razorpay_test"], indirect=True)
def test_missing_refund_response_and_out_of_order_signed_webhooks_recover_with_get_only(flow):
    provider, calls, refund = gateway_return(flow)
    original = provider.transport

    def timeout(method, path, data, headers):
        result = original(method, path, data, headers)
        if method == "POST":
            raise ProviderError("provider_outcome_unknown")
        return result

    provider.transport = timeout
    assert (
        call(flow, "payments/refunds/execute", {"gateway_refund_approved": True}).status_code == 503
    )
    refund["status"] = "processed"
    for event_id, event_type in [
        ("evt_early", "refund.processed"),
        ("evt_late", "refund.failed"),
        ("evt_early", "refund.processed"),
    ]:
        # Synthetic signed events are used ONLY in this disposable test database.
        raw = json.dumps(
            {
                "event": event_type,
                "payload": {
                    "refund": {"entity": {"id": refund["id"], "payment_id": "pay_fixture"}}
                },
            }
        ).encode()
        response = flow["client"].post(
            "/api/payments/webhook",
            content=raw,
            headers={
                "x-razorpay-event-id": event_id,
                "x-razorpay-signature": hmac.new(
                    b"fixture-webhook", raw, hashlib.sha256
                ).hexdigest(),
            },
        )
        assert response.status_code == 200, response.text
    result = view(flow)
    assert result["refund"]["status"] == "processed"
    assert result["deposit_refunded_paise"] == 50000
    assert sum(method == "POST" for method, _ in calls) == 1
    with flow["factory"]() as db:
        attempts = db.scalars(select(RefundAttempt)).all()
        assert len(attempts) == 2
        assert attempts[0].idempotency_key == attempts[1].idempotency_key
        assert db.scalar(select(RefundIntent)).provider_refund_id == "rfnd_final"
    assert_balanced(flow)
