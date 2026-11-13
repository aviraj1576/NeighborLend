"""Sandbox authority is checked at startup, dispatch, and application boundaries.

All gateway I/O uses synthetic transport; no external payment operation occurs.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import select
from test_razorpay_escrow import call, razorpay_flow
from test_razorpay_escrow import flow as payment_flow

from app.config import Settings
from app.payment_models import JournalTransaction, PaymentTransaction, RefundIntent, RentalBooking
from app.services.payments import PaymentService
from app.services.razorpay_service import (
    MockPaymentProvider,
    ProviderError,
    RazorpayTestProvider,
    configured_provider,
)

flow = payment_flow


def test_missing_provider_defaults_to_disabled_without_gateway_credentials(monkeypatch):
    monkeypatch.delenv("PAYMENT_PROVIDER", raising=False)
    config = Settings(
        _env_file=None,
        payment_demo_mode=False,
        razorpay_key_id="",
        razorpay_key_secret="",
        razorpay_webhook_secret="",
    )
    assert configured_provider(config).kind == "disabled"
    assert configured_provider(config).sandbox_only is True


def test_direct_mock_adapter_cannot_bypass_explicit_configuration(monkeypatch):
    config = settings(
        payment_provider="disabled",
        razorpay_key_id="",
        razorpay_key_secret="",
        razorpay_webhook_secret="",
    )
    monkeypatch.setattr("app.config.get_settings", lambda: config)
    with pytest.raises(ProviderError, match="conflicting_payment_modes"):
        MockPaymentProvider().create_order(
            SimpleNamespace(id="booking", total_amount_paise=100), "reference"
        )


def settings(**changes):
    return Settings(
        _env_file=None,
        **{
            "app_env": "test",
            "payment_provider": "razorpay_test",
            "payment_demo_mode": False,
            "razorpay_key_id": "rzp_test_fixture",
            "razorpay_key_secret": "synthetic-secret",
            "razorpay_webhook_secret": "synthetic-webhook",
            "auto_migrate": False,
            **changes,
        },
    )


@pytest.mark.parametrize("provider", ["razorpay", "razorpay_live", "live", "stripe", "", None])
def test_unknown_or_ambiguous_provider_configuration_is_rejected(provider):
    with pytest.raises(ValidationError):
        settings(payment_provider=provider)


@pytest.mark.parametrize(
    "changes",
    [
        {"razorpay_key_id": "rzp_live_FORBIDDEN"},
        {"payment_provider": "disabled", "razorpay_key_id": "rzp_live_FORBIDDEN"},
        {"payment_provider": "mock", "razorpay_key_id": "rzp_live_FORBIDDEN"},
        {"razorpay_key_id": ""},
        {"razorpay_key_secret": ""},
        {"razorpay_webhook_secret": ""},
        {"razorpay_key_secret": " "},
        {"payment_demo_mode": True},
        {"payment_provider": "mock", "payment_demo_mode": True},
    ],
)
def test_invalid_configuration_aborts_actual_app_startup(changes, monkeypatch, tmp_path):
    import app.main as main

    monkeypatch.setattr(main, "settings", settings(upload_dir=str(tmp_path / "unused"), **changes))
    with pytest.raises(ProviderError):
        with TestClient(main.app):
            pytest.fail("Invalid configuration started the application")
    assert not (tmp_path / "unused").exists()  # Rejected before startup side effects.


@pytest.mark.parametrize("provider", ["disabled", "mock", "razorpay_test"])
def test_supported_startup_modes_are_offline_and_sandbox_only(provider, monkeypatch, tmp_path):
    import app.main as main

    changes = {"payment_provider": provider, "upload_dir": str(tmp_path / "uploads")}
    if provider in {"disabled", "mock"}:
        changes.update(
            razorpay_key_id="",
            razorpay_key_secret="",
            razorpay_webhook_secret="",
            payment_demo_mode=provider == "mock",
        )
    config = settings(**changes)
    monkeypatch.setattr(main, "settings", config)
    monkeypatch.setattr(main, "_preload_model", lambda: pytest.fail("AI must not be loaded"))
    with TestClient(main.app) as client:
        assert client.get("/api/health").status_code == 200
    assert configured_provider(config).sandbox_only is True


OPERATIONS = [
    lambda p: p.create_order(SimpleNamespace(id="booking", total_amount_paise=100), "reference"),
    lambda p: p.fetch_order("order_fixture"),
    lambda p: p.find_order("reference"),
    lambda p: p.order_payments("order_fixture"),
    lambda p: p.fetch_payment("pay_fixture"),
    lambda p: p.refund("pay_fixture", 100, "reference"),
    lambda p: p.fetch_refund("rfnd_fixture"),
    lambda p: p.verify_checkout("order_fixture", "pay_fixture", "0" * 64),
    lambda p: p.verify_webhook(b"{}", "0" * 64),
]


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize(
    "injection", ["adapter_live_key", "configuration_live_key", "provider", "secret", "demo_mode"]
)
def test_runtime_injection_blocks_every_operation_before_transport(operation, injection):
    config = settings()
    calls = []
    provider = RazorpayTestProvider(config, transport=lambda *args: calls.append(args) or {})
    if injection == "adapter_live_key":
        provider.key_id = "rzp_live_FORBIDDEN"
    elif injection == "configuration_live_key":
        config.razorpay_key_id = "rzp_live_FORBIDDEN"
    elif injection == "provider":
        config.payment_provider = "disabled"
    elif injection == "secret":
        config.razorpay_key_secret = SecretStr("changed-synthetic-secret")
    else:
        config.payment_demo_mode = True
    with pytest.raises(ProviderError):
        operation(provider)
    assert calls == []


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "payments/pay_fixture/capture"),
        ("POST", "payouts"),
        ("POST", "transfers"),
        ("POST", "orders/order_fixture/transfers"),
        ("POST", "accounts"),
        ("GET", "https://example.invalid/payments"),
        ("GET", "orders/../payouts"),
        ("DELETE", "orders/order_fixture"),
    ],
)
def test_gateway_dispatch_has_no_capture_payout_or_transfer_path(method, path):
    provider = RazorpayTestProvider(
        settings(), transport=lambda *args: pytest.fail("Unsupported endpoint dispatched")
    )
    with pytest.raises(ProviderError, match="unsupported_provider_operation"):
        provider._request(method, path, {} if method == "POST" else None)


@pytest.mark.parametrize("response", [{"livemode": True}, {"items": [{"livemode": True}]}])
def test_provider_cannot_reconcile_live_mode_entities(response):
    provider = RazorpayTestProvider(settings(), transport=lambda *args: response)
    with pytest.raises(ProviderError, match="live_provider_response_forbidden"):
        provider.fetch_order("order_fixture")


def test_native_https_dispatch_uses_fixed_official_host_and_no_proxies_or_redirects(monkeypatch):
    import base64
    import json
    from urllib.request import ProxyHandler

    from app.services.razorpay_service import NoRedirect

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            return b'{"id":"order_fixture"}'

    class Opener:
        def open(self, request, timeout):
            assert request.full_url == "https://api.razorpay.com/v1/orders"
            assert request.method == "POST" and timeout == 15
            assert json.loads(request.data)["amount"] == 100
            assert json.loads(request.data)["currency"] == "INR"
            token = request.get_header("Authorization").removeprefix("Basic ")
            assert base64.b64decode(token).decode().split(":", 1)[0] == "rzp_test_fixture"
            return Response()

    def opener(*handlers):
        assert any(isinstance(h, ProxyHandler) and h.proxies == {} for h in handlers)
        assert any(isinstance(h, NoRedirect) for h in handlers)
        return Opener()

    monkeypatch.setattr("app.services.razorpay_service.build_opener", opener)
    result = RazorpayTestProvider(settings()).create_order(
        SimpleNamespace(id="booking", total_amount_paise=100), "reference"
    )
    assert result["id"] == "order_fixture"


@pytest.mark.parametrize("amount", [True, 1.5, 0, -1, 1_000_000_001, "100", float("nan")])
def test_invalid_amount_never_reaches_provider_transport(amount):
    provider = RazorpayTestProvider(
        settings(), transport=lambda *args: pytest.fail("Invalid amount dispatched")
    )
    with pytest.raises(ProviderError, match="invalid_provider_amount"):
        provider.create_order(SimpleNamespace(id="booking", total_amount_paise=amount), "reference")
    with pytest.raises(ProviderError, match="invalid_provider_amount"):
        provider.refund("pay_fixture", amount, "reference")


@pytest.mark.parametrize(
    "changes",
    [
        {"total_amount_paise": True},
        {"total_amount_paise": 100.0},
        {"currency": "USD"},
        {"total_amount_paise": 101},
        {"security_deposit_paise": -1},
        {"duration_days": 0},
        {"daily_rate_paise": 0},
        {"rental_fee_paise": -100},
    ],
)
def test_application_revalidates_booking_snapshot_before_dispatch(changes):
    booking = SimpleNamespace(
        **{
            "provider": "razorpay_test",
            "duration_days": 1,
            "daily_rate_paise": 100,
            "rental_fee_paise": 100,
            "security_deposit_paise": 0,
            "total_amount_paise": 100,
            "currency": "INR",
            **changes,
        }
    )
    with pytest.raises(HTTPException) as exc:
        PaymentService(None, configured_provider(settings()))._mode(booking)
    assert exc.value.status_code == 409


def test_backend_amounts_and_flags_cannot_be_supplied_by_frontend(flow):
    for tampering in (
        {"amount_paise": 1},
        {"currency": "USD"},
        {"provider": "razorpay_test"},
        {"sandbox_only": True},
        {"key_id": "rzp_live_FORBIDDEN"},
    ):
        assert call(flow, "payments/create-order", tampering).status_code == 422
    result = call(flow, "payments/create-order").json()
    assert result["sandbox_only"] is result["test_mode"] is True
    assert result["simulated_escrow"] is True
    assert result["amount_paise"] == flow["booking"]["total_amount_paise"] == 90000
    assert result["currency"] == "INR"
    assert call(flow, "payments/create-order").json()["order_id"] == result["order_id"]
    with flow["factory"]() as db:
        assert len(list(db.scalars(select(PaymentTransaction)))) == 1


@pytest.mark.parametrize("role", ["other", "lender"])
@pytest.mark.parametrize("route", ["create-order", "verify", "reconcile"])
def test_unauthorized_payment_paths_never_contact_provider(flow, role, route):
    extra = (
        {"order_id": "order_fixture", "payment_id": "pay_fixture", "signature": "0" * 64}
        if route == "verify"
        else {}
    )
    assert call(flow, "payments/" + route, extra, role=role).status_code == 403
    with flow["factory"]() as db:
        assert db.scalar(select(PaymentTransaction)) is None
        assert db.scalar(select(JournalTransaction)) is None


def test_unauthorized_refunds_cannot_create_intent_or_dispatch(flow):
    assert call(flow, "payments/refund-deposit", role="other").status_code == 403
    assert call(flow, "payments/refunds/reconcile", role="other").status_code == 403
    assert call(flow, "payments/refunds/reconcile").status_code == 409
    assert call(flow, "payments/refund-deposit").status_code == 403
    with flow["factory"]() as db:
        assert db.scalar(select(RefundIntent)) is None
        assert db.scalar(select(JournalTransaction)) is None


@pytest.mark.parametrize("flow", ["razorpay_test"], indirect=True)
def test_abandoned_real_checkout_has_no_payment_or_handover_authority(flow):
    razorpay_flow(flow)
    order = call(flow, "payments/create-order")
    assert order.status_code == 200
    # Dismissing the official widget sends no confirmation to the backend.
    view = (
        flow["client"]
        .get(f"/api/payments/bookings/{flow['booking']['id']}", headers=flow["headers"]["borrower"])
        .json()
    )
    assert view["payment_status"] == "order_created"
    assert view["handover_unlocked"] is False
    assert view["sandbox_only"] is True
    denied = flow["client"].post(
        f"/api/borrow-requests/{flow['request_id']}/handover/borrower-confirm",
        json={},
        headers=flow["headers"]["borrower"],
    )
    assert denied.status_code == 409
    with flow["factory"]() as db:
        assert db.get(RentalBooking, flow["booking"]["id"]).booking_status == "awaiting_payment"
        assert db.scalar(select(JournalTransaction)) is None
        assert all(t.transaction_type == "order" for t in db.scalars(select(PaymentTransaction)))
