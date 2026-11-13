"""Audit regressions with authenticated API calls, real DB locks and controlled I/O."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Event

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select, text
from test_razorpay_escrow import assert_balanced, call, evidence, fund, physical_return
from test_razorpay_escrow import flow as payment_flow

from app.config import Settings
from app.main import app
from app.models import BorrowRequest, NegotiationOffer
from app.payment_models import (
    JournalTransaction,
    RefundAttempt,
    RefundIntent,
    RentalBooking,
)
from app.routers.payments import payment_provider
from app.services.payments import PaymentService
from app.services.razorpay_service import (
    DisabledPaymentProvider,
    ProviderError,
    configured_provider,
)

flow = payment_flow


def state(flow):
    return (
        flow["client"]
        .get(f"/api/payments/bookings/{flow['booking']['id']}", headers=flow["headers"]["borrower"])
        .json()
    )


def claim(flow):
    assert (
        call(
            flow,
            "disputes/raise",
            {"claimed_deduction_paise": 20000, "reason": "Human condition claim"},
            "lender",
        ).status_code
        == 200
    )


def authorized_refund(flow):
    fund(flow)
    physical_return(flow)
    claim(flow)
    assert call(flow, "disputes/respond", {"accepted": True}).status_code == 200
    assert (
        call(
            flow,
            "disputes/settle",
            {
                "approved_deduction_paise": 20000,
                "reason": "Independent review of return photographs",
            },
            "admin",
        ).status_code
        == 200
    )


def test_disabled_configuration_and_live_key_rejection():
    assert Settings.model_fields["payment_provider"].default == "disabled"
    assert (
        configured_provider(Settings(_env_file=None, payment_provider="disabled")).kind
        == "disabled"
    )
    secret = "synthetic-private-public-jwt-0123456789-ABCDEFGHIJK"
    for provider in ("disabled", "mock", "razorpay_test"):
        with pytest.raises(ProviderError, match="only_test_keys_allowed"):
            configured_provider(
                Settings(
                    _env_file=None, payment_provider=provider, razorpay_key_id="rzp_live_forbidden"
                )
            )
    public = dict(
        _env_file=None,
        app_env="production",
        deployment_exposure="public",
        jwt_secret=secret,
        payment_provider="disabled",
    )
    assert configured_provider(Settings(**public)).kind == "disabled"
    with pytest.raises(ProviderError, match="mock_requires"):
        configured_provider(
            Settings(**{**public, "payment_provider": "mock"}, payment_demo_mode=True)
        )
    for secret in ("neighborlend-super-secret-key-2026-prototype", "a" * 64, "short"):
        # Invalid JWT settings now fail before any provider can be constructed,
        # including local development and isolated test configurations.
        with pytest.raises(ValidationError, match="JWT_SECRET"):
            configured_provider(
                Settings(_env_file=None, deployment_exposure="public", jwt_secret=secret)
            )


def test_disabled_mode_preserves_private_inspection_and_intent_recovery(flow):
    fund(flow)
    app.dependency_overrides[payment_provider] = lambda: DisabledPaymentProvider()
    assert state(flow)["operations_enabled"] is False
    assert call(flow, "payments/create-order").status_code == 503
    assert call(flow, "payments/mock-confirm").status_code == 403
    assert call(flow, "payments/cancel").status_code == 200
    assert call(flow, "payments/refunds/reconcile").status_code == 503
    assert state(flow)["refund"]["status"] == "created"
    app.dependency_overrides[payment_provider] = lambda: flow["provider"]
    assert call(flow, "payments/refunds/reconcile").json()["booking_status"] == "cancelled"


def test_remote_and_proxy_requests_cannot_reach_local_mock(flow):
    async def request(client, headers=None):
        transport = httpx.ASGITransport(app=app, client=client)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://localhost"
        ) as connection:
            return await connection.get("/api/health", headers=headers)

    assert asyncio.run(request(("203.0.113.5", 1000))).status_code == 403
    assert (
        asyncio.run(request(("127.0.0.1", 1000), {"x-forwarded-for": "203.0.113.5"})).status_code
        == 403
    )


def test_mock_checkout_cancelled_then_retry(flow):
    assert call(flow, "payments/create-order").status_code == 200
    cancelled = call(flow, "payments/mock-confirm", {"outcome": "cancelled"}).json()
    assert cancelled["payment_status"] == "failed" and not cancelled["handover_unlocked"]
    assert call(flow, "payments/mock-confirm").json()["payment_status"] == "captured"
    assert_balanced(flow)


def test_legacy_return_cannot_strand_managed_rental(flow):
    fund(flow)
    # Reach active handover, then exercise the old route before submitting return evidence.
    before = evidence(flow, "handover", "lender")
    base = f"/api/borrow-requests/{flow['request_id']}"
    for path, role, data in (
        ("handover/upload-photos", "lender", {"photo_urls": [before]}),
        ("handover/borrower-confirm", "borrower", {}),
        ("handover/lender-confirm", "lender", None),
    ):
        assert (
            flow["client"]
            .post(base + "/" + path, json=data, headers=flow["headers"][role])
            .status_code
            == 200
        )
    assert (
        flow["client"].post(base + "/return", headers=flow["headers"]["lender"]).status_code == 410
    )
    after = evidence(flow, "return", "borrower")
    assert (
        flow["client"]
        .post(
            base + "/return/upload-photos",
            json={"photo_urls": [after]},
            headers=flow["headers"]["borrower"],
        )
        .status_code
        == 200
    )


@pytest.mark.parametrize("role", ["borrower", "lender"])
def test_generic_dispute_freezes_and_requires_admin(flow, role):
    fund(flow)
    physical_return(flow)
    result = flow["client"].post(
        f"/api/borrow-requests/{flow['request_id']}/dispute",
        json={"description": "Platform recovery requested"},
        headers=flow["headers"][role],
    )
    assert result.status_code == 200, result.text
    view = state(flow)
    assert view["deposit_state"] == "frozen" and view["dispute"]["status"] == "escalated"
    assert (
        call(flow, "disputes/settle", {"approved_deduction_paise": 0}, "lender").status_code == 403
    )
    assert (
        call(flow, "disputes/settle", {"approved_deduction_paise": 0}, "admin").status_code == 422
    )
    assert (
        call(
            flow,
            "disputes/settle",
            {"approved_deduction_paise": 0, "reason": "Reviewed and dismissed claim"},
            "admin",
        ).status_code
        == 200
    )
    assert call(flow, "payments/refunds/reconcile").json()["deposit_refunded_paise"] == 50000
    assert_balanced(flow)


def test_borrower_rejection_cannot_be_reversed_without_admin(flow):
    fund(flow)
    physical_return(flow)
    claim(flow)
    assert (
        call(flow, "disputes/respond", {"accepted": False, "notes": "Reject claim"}).json()[
            "status"
        ]
        == "escalated"
    )
    assert call(flow, "disputes/respond", {"accepted": True}).status_code == 409
    assert (
        call(flow, "disputes/settle", {"approved_deduction_paise": 20000}, "lender").status_code
        == 403
    )
    assert call(flow, "payments/refund-deposit", role="lender").status_code == 409
    assert call(flow, "payments/refunds/reconcile").status_code == 409
    assert (
        call(
            flow,
            "disputes/settle",
            {"approved_deduction_paise": 10000, "reason": "Reviewed both parties and photographs"},
            "admin",
        ).status_code
        == 200
    )
    original = state(flow)["dispute"]
    assert (
        call(
            flow, "disputes/settle", {"approved_deduction_paise": 10000, "reason": "Retry"}, "admin"
        ).status_code
        == 200
    )
    assert state(flow)["dispute"] == original
    assert call(flow, "payments/refunds/reconcile").json()["deposit_refunded_paise"] == 40000


def test_admin_dismisses_abandoned_return_draft(flow):
    fund(flow)
    physical_return(flow)
    result = flow["client"].post(
        f"/api/borrow-requests/{flow['request_id']}/return/confirm",
        json={"approved": False, "condition_note": "Needs review"},
        headers=flow["headers"]["lender"],
    )
    assert result.status_code == 200, result.text
    assert state(flow)["dispute"]["status"] == "needs_claim"
    assert (
        call(
            flow,
            "disputes/settle",
            {
                "approved_deduction_paise": 0,
                "reason": "No substantiated damage claim; release deposit",
            },
            "admin",
        ).status_code
        == 200
    )
    assert call(flow, "payments/refunds/reconcile").json()["held_deposit_paise"] == 0


def test_return_approval_and_intent_are_atomic_and_recoverable(flow, monkeypatch):
    fund(flow)
    physical_return(flow)
    original = PaymentService._intent

    def crash(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError("synthetic crash before commit")

    with monkeypatch.context() as patch:
        patch.setattr(PaymentService, "_intent", crash)
        with flow["factory"]() as db, pytest.raises(RuntimeError):
            PaymentService(db, flow["provider"]).return_decision(
                flow["booking"]["id"], flow["ids"]["lender"], True
            )
    with flow["factory"]() as db:
        assert db.get(BorrowRequest, flow["request_id"]).handover_status == "return_photos_uploaded"
        assert db.scalar(select(RefundIntent)) is None
        PaymentService(db, flow["provider"]).return_decision(
            flow["booking"]["id"], flow["ids"]["lender"], True, "Clean item"
        )
    assert state(flow)["refund"]["status"] == "created"
    assert call(flow, "payments/refunds/reconcile").json()["booking_status"] == "completed"


def test_private_evidence_cannot_be_forged_or_read_by_others(flow):
    fund(flow)
    reference = evidence(flow, "handover", "lender")
    client, headers = flow["client"], flow["headers"]
    assert client.get(reference).status_code == 401
    assert client.get(reference, headers=headers["other"]).status_code == 403
    assert client.get(reference, headers=headers["admin"]).headers["content-type"] == "image/png"
    path = f"/api/borrow-requests/{flow['request_id']}/handover/upload-photos"
    assert (
        client.post(
            path,
            json={"photo_urls": ["https://unrelated.invalid/photo.png"]},
            headers=headers["lender"],
        ).status_code
        == 422
    )
    assert (
        client.post(path, json={"photo_urls": [reference]}, headers=headers["lender"]).status_code
        == 200
    )
    public = client.get(f"/api/borrow-requests/{flow['request_id']}").json()
    assert public["handover_photos"] == []
    response = client.post(
        f"/api/borrow-requests/{flow['request_id']}/handover/borrower-confirm",
        json={"condition_note": "Received, surface checked"},
        headers=headers["borrower"],
    )
    assert response.json()["handover_condition_note"] == "Received, surface checked"
    assert response.json()["borrowing_started_at"] is None


@pytest.mark.parametrize("action", ["continue", "return", "cancel"])
def test_post_receipt_handover_issue_has_platform_recovery(flow, action):
    fund(flow)
    base = f"/api/borrow-requests/{flow['request_id']}/handover"
    reference = evidence(flow, "handover", "lender")
    for path, role, data in (
        ("upload-photos", "lender", {"photo_urls": [reference]}),
        ("borrower-confirm", "borrower", {}),
        ("report-issue", "borrower", {"description": "Receipt issue"}),
    ):
        assert (
            flow["client"]
            .post(base + "/" + path, json=data, headers=flow["headers"][role])
            .status_code
            == 200
        )
    payload = {"action": action, "reason": "Reviewed item custody and agreed recovery"}
    assert call(flow, "disputes/handover-issue/resolve", payload, "lender").status_code == 403
    assert call(flow, "disputes/handover-issue/resolve", payload, "admin").status_code == 200
    if action == "cancel":
        assert call(flow, "payments/refunds/reconcile").json()["refund"]["amount_paise"] == 90000
    else:
        rental = (
            flow["client"]
            .get(
                f"/api/payments/requests/{flow['request_id']}/rental",
                headers=flow["headers"]["borrower"],
            )
            .json()
        )
        assert rental["handover_status"] == (
            "borrower_confirmed" if action == "continue" else "lender_confirmed"
        )


def test_cancelled_rental_is_private_but_recovery_accessible(flow):
    fund(flow)
    assert call(flow, "payments/cancel").status_code == 200
    private = f"/api/payments/requests/{flow['request_id']}/rental"
    assert flow["client"].get(f"/api/borrow-requests/{flow['request_id']}").status_code == 404
    assert flow["client"].get(private).status_code == 401
    assert flow["client"].get(private, headers=flow["headers"]["other"]).status_code == 403
    for role in ("borrower", "lender", "admin"):
        assert flow["client"].get(private, headers=flow["headers"][role]).status_code == 200


def test_definite_order_failure_can_retry_but_unknown_is_not_blindly_created(flow, monkeypatch):
    provider = flow["provider"]
    original = provider.create_order
    calls = []

    def create(booking, reference):
        calls.append(reference)
        if len(calls) == 1:
            raise ProviderError("synthetic definite rejection", definite=True)
        return original(booking, reference)

    monkeypatch.setattr(provider, "create_order", create)
    assert call(flow, "payments/create-order").status_code == 503
    assert call(flow, "payments/create-order").status_code == 200
    assert len(calls) == 2


def test_delayed_order_result_cannot_downgrade_capture(flow):
    started, release = Event(), Event()
    base = flow["provider"]

    class DelayedProvider:
        kind, key_id = "mock", None

        @property
        def sandbox_only(self):
            return base.sandbox_only

        def create_order(self, booking, reference):
            started.set()
            assert release.wait(10)
            return base.create_order(booking, reference)

    def delayed():
        with flow["factory"]() as db:
            return PaymentService(db, DelayedProvider()).order(
                flow["booking"]["id"], flow["ids"]["borrower"]
            )

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(delayed)
        try:
            assert started.wait(10)
            assert call(flow, "payments/create-order").status_code == 200
            assert call(flow, "payments/mock-confirm").json()["payment_status"] == "captured"
        finally:
            release.set()
        future.result(timeout=10)
    assert state(flow)["payment_status"] == "captured"
    assert_balanced(flow)


def test_concurrent_capture_posts_one_funding_journal(flow):
    assert call(flow, "payments/create-order").status_code == 200

    def pay(_):
        with flow["factory"]() as db:
            return PaymentService(db, flow["provider"]).demo_pay(
                flow["booking"]["id"], flow["ids"]["borrower"], "success"
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(row["payment_status"] == "captured" for row in pool.map(pay, range(2)))
    with flow["factory"]() as db:
        assert len(db.scalars(select(JournalTransaction)).all()) == 1


def test_expired_refund_lease_fences_delayed_pending_response(flow):
    authorized_refund(flow)
    started, release = Event(), Event()
    base = flow["provider"]

    class DelayedProvider:
        kind = "mock"

        @property
        def sandbox_only(self):
            return base.sandbox_only

        def refund(self, *args):
            started.set()
            assert release.wait(10)
            return base.refund(*args)

    def delayed():
        with flow["factory"]() as db:
            return PaymentService(db, DelayedProvider()).execute_refund(
                flow["booking"]["id"], flow["ids"]["admin"], "pending", admin=True
            )

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(delayed)
        try:
            assert started.wait(10)
            assert call(flow, "payments/refunds/reconcile").status_code == 409
            with flow["factory"]() as db:
                attempt = db.scalar(select(RefundAttempt))
                attempt.created_at = datetime.utcnow() - timedelta(seconds=31)
                db.commit()
            assert (
                call(flow, "payments/refunds/reconcile").json()["refund"]["status"] == "processed"
            )
        finally:
            release.set()
        assert future.result(timeout=10)["refund"]["status"] == "processed"
    final = state(flow)
    assert final["refund"]["status"] == "processed" and final["deposit_refunded_paise"] == 30000
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


def test_refund_ownership_amount_bounds_and_database_allocation_guards(flow):
    authorized_refund(flow)
    assert call(flow, "payments/refunds/reconcile", role="other").status_code == 403
    assert call(flow, "payments/refunds/reconcile", {"amount_paise": 90000}).status_code == 422
    with flow["factory"]() as db:
        with pytest.raises(Exception, match="immutable financial terms"):
            db.execute(text("UPDATE refund_intents SET amount_paise=90000"))
            db.commit()
        db.rollback()
    assert call(flow, "payments/refunds/reconcile").json()["deposit_refunded_paise"] == 30000
    for _ in range(3):
        assert call(flow, "payments/refunds/reconcile").json()["deposit_refunded_paise"] == 30000
    assert_balanced(flow)


def test_negotiated_deposit_survives_listing_changes_and_terms_are_immutable(flow):
    with flow["factory"]() as db:
        booking = db.get(RentalBooking, flow["booking"]["id"])
        offer = db.get(NegotiationOffer, booking.offer_id)
        listing_id, conversation_id = booking.listing_id, offer.conversation_id
    start = datetime.utcnow() + timedelta(days=20)
    proposed = flow["client"].post(
        f"/api/conversations/{conversation_id}/offers",
        headers=flow["headers"]["borrower"],
        json={
            "listing_id": listing_id,
            "daily_price": 123.45,
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=2)).isoformat(),
        },
    )
    assert proposed.status_code == 200, proposed.text
    terms = proposed.json()
    assert terms["security_deposit_paise"] == 50000 and terms["total_amount_paise"] == 74690
    assert (
        flow["client"]
        .patch(
            f"/api/listings/{listing_id}",
            json={"security_deposit": 900},
            headers=flow["headers"]["lender"],
        )
        .status_code
        == 200
    )
    accepted = flow["client"].post(
        f"/api/offers/{terms['id']}/accept", headers=flow["headers"]["lender"]
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["security_deposit_paise"] == 50000
    with flow["factory"]() as db:
        with pytest.raises(Exception, match="immutable financial terms"):
            db.execute(
                text("UPDATE negotiation_offers SET security_deposit_paise=90000 WHERE id=:id"),
                {"id": terms["id"]},
            )
            db.commit()


@pytest.mark.parametrize("outcome", ["failed", "pending"])
@pytest.mark.parametrize(
    "route,body",
    [
        ("upload-photos", {"photo_urls": ["/uploads/forged.png"]}),
        ("borrower-confirm", {}),
        ("lender-confirm", None),
        ("report-issue", {"description": "Unpaid issue"}),
        ("mark-given", None),
        ("confirm", None),
    ],
)
def test_every_handover_mutation_rejects_uncaptured_payment(flow, outcome, route, body):
    call(flow, "payments/create-order")
    call(flow, "payments/mock-confirm", {"outcome": outcome})
    result = flow["client"].post(
        f"/api/borrow-requests/{flow['request_id']}/handover/{route}",
        json=body,
        headers=flow["headers"]["lender"],
    )
    assert result.status_code == 409, result.text


def test_refund_provider_overpayment_and_unrelated_payment_are_rejected(flow, monkeypatch):
    authorized_refund(flow)
    base = flow["provider"].refund

    def excessive(*args):
        result = base(*args)
        result["amount"] = 90000
        return result

    monkeypatch.setattr(flow["provider"], "refund", excessive)
    assert call(flow, "payments/refunds/reconcile").status_code == 503
    assert state(flow)["deposit_refunded_paise"] == 0

    def unrelated(*args):
        result = base(*args)
        result["payment_id"] = "pay_other"
        return result

    monkeypatch.setattr(flow["provider"], "refund", unrelated)
    assert call(flow, "payments/refunds/reconcile").status_code == 503
    assert state(flow)["held_deposit_paise"] == 50000
    monkeypatch.setattr(flow["provider"], "refund", base)
    assert call(flow, "payments/refunds/reconcile").json()["deposit_refunded_paise"] == 30000


def test_stale_claim_consent_is_rejected(flow):
    fund(flow)
    physical_return(flow)
    claim(flow)
    version = state(flow)["dispute"]["claim_version"]
    assert (
        call(
            flow,
            "disputes/raise",
            {
                "claimed_deduction_paise": 30000,
                "reason": "Revised human claim with additional detail",
            },
            "lender",
        ).status_code
        == 200
    )
    assert (
        call(flow, "disputes/respond", {"accepted": True, "claim_version": version}).status_code
        == 409
    )
    assert state(flow)["dispute"]["borrower_accepted"] is False


def test_disabled_backend_lifespan_starts_without_gateway_credentials(flow, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import app.main as main

    settings = Settings(
        _env_file=None,
        app_env="test",
        payment_provider="disabled",
        razorpay_key_id="",
        razorpay_key_secret="",
        razorpay_webhook_secret="",
        auto_migrate=False,
        upload_dir=str(tmp_path / "startup-uploads"),
    )
    monkeypatch.setattr(main, "settings", settings)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
