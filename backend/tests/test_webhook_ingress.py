"""Test-only ingress must authenticate exact bytes and expose one endpoint only."""

import asyncio
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_razorpay_escrow import assert_balanced, call, physical_return, razorpay_flow
from test_razorpay_escrow import flow as payment_flow

from app.config import BACKEND_DIR, BASE_DIR, Settings
from app.main import app as private_app
from app.payment_models import JournalTransaction, ProcessedWebhook, RefundIntent, RentalBooking
from app.routers.payments import payment_provider
from app.services.razorpay_service import ProviderError
from app.webhook_ingress import UPSTREAM, TestWebhookIngress

flow = payment_flow
SECRET = b"fixture-webhook"
RAW = b'{"event":"refund.created","payload":{"refund":{"entity":{"id":"rfnd_SyntheticCreated"}}}}'


def settings(**changes):
    return Settings(
        _env_file=None,
        **{
            "app_env": "test",
            "payment_provider": "razorpay_test",
            "payment_demo_mode": False,
            "deployment_exposure": "local",
            "razorpay_key_id": "rzp_test_fixture",
            "razorpay_key_secret": "synthetic-key-secret",
            "razorpay_webhook_secret": SECRET.decode(),
            **changes,
        },
    )


def signed(raw=RAW, event_id="evt_ingress"):
    return {
        "x-razorpay-signature": hmac.new(SECRET, raw, hashlib.sha256).hexdigest(),
        "x-razorpay-event-id": event_id,
    }


def test_absolute_env_paths_and_precedence(tmp_path, monkeypatch):
    assert Settings.model_config["env_file"] == (BASE_DIR / ".env", BACKEND_DIR / ".env")
    shared, backend = tmp_path / "shared.env", tmp_path / "backend.env"
    shared.write_text("RAZORPAY_KEY_ID=rzp_test_shared\n", encoding="utf-8")
    backend.write_text("RAZORPAY_KEY_ID=rzp_test_backend\n", encoding="utf-8")
    monkeypatch.delenv("RAZORPAY_KEY_ID")
    assert Settings(_env_file=(shared, backend)).razorpay_key_id == "rzp_test_backend"
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_process")
    assert Settings(_env_file=(shared, backend)).razorpay_key_id == "rzp_test_process"


@pytest.mark.parametrize(
    "changes",
    [
        {"payment_provider": "disabled"},
        {"payment_provider": "mock"},
        {"app_env": "production"},
        {"deployment_exposure": "public"},
        {"razorpay_key_id": "rzp_live_forbidden"},
        {"razorpay_webhook_secret": ""},
    ],
)
def test_ingress_refuses_non_test_configuration(changes):
    with pytest.raises(ProviderError):
        TestWebhookIngress(settings(**changes))


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/payments/webhook"),
        ("OPTIONS", "/api/payments/webhook"),
        ("POST", "/api/payments/webhook/"),
        ("POST", "/api/payments/%77ebhook"),
        ("POST", "/api/payments/webhook?forward=/api/admin"),
        ("GET", "/api/health"),
        ("GET", "/docs"),
        ("GET", "/openapi.json"),
        ("POST", "/api/payments/create-order"),
        ("POST", "/api/auth/login"),
        ("GET", "/api/disputes/admin"),
        ("GET", "/uploads/file"),
    ],
)
def test_ingress_does_not_route_other_paths_or_methods(method, path):
    calls = []
    with TestClient(
        TestWebhookIngress(
            settings(),
            transport=httpx.MockTransport(
                lambda request: calls.append(request) or httpx.Response(200)
            ),
        )
    ) as client:
        assert client.request(method, path, content=RAW, headers=signed()).status_code == 404
    assert calls == []


@pytest.mark.parametrize(
    "headers,body",
    [
        ({}, RAW),
        ({**signed(), "x-razorpay-signature": "0" * 64}, RAW),
        (signed(), RAW + b" "),
        ({**signed(), "x-razorpay-event-id": ""}, RAW),
        ({**signed(), "content-encoding": "gzip"}, RAW),
        (list(signed().items()) + [("x-razorpay-signature", "0" * 64)], RAW),
    ],
)
def test_invalid_authentication_never_reaches_private_api(headers, body):
    calls = []
    with TestClient(
        TestWebhookIngress(
            settings(),
            transport=httpx.MockTransport(
                lambda request: calls.append(request) or httpx.Response(200)
            ),
        )
    ) as client:
        assert (
            client.post("/api/payments/webhook", content=body, headers=headers).status_code == 400
        )
    assert calls == []


def test_proxy_preserves_bytes_strips_untrusted_headers_and_sends_no_credentials():
    raw = RAW + b"\n "
    calls = []

    def upstream(request):
        calls.append(request)
        assert str(request.url) == UPSTREAM
        assert request.content == raw
        assert request.headers["host"] == "127.0.0.1:8001"
        assert request.headers["x-razorpay-signature"] == signed(raw)["x-razorpay-signature"]
        for name in (
            "authorization",
            "cookie",
            "forwarded",
            "x-forwarded-for",
            "x-forwarded-host",
            "x-evil",
        ):
            assert name not in request.headers
        return httpx.Response(200, json={"received": True}, headers={"Set-Cookie": "untrusted=1"})

    with TestClient(
        TestWebhookIngress(settings(), transport=httpx.MockTransport(upstream))
    ) as client:
        response = client.post(
            "/api/payments/webhook",
            content=raw,
            headers={
                **signed(raw),
                "Host": "public.example.test",
                "Authorization": "Bearer fake",
                "Cookie": "fake=1",
                "Forwarded": "for=attacker",
                "X-Forwarded-For": "attacker",
                "X-Forwarded-Host": "attacker",
                "X-Evil": "drop",
            },
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert "set-cookie" not in response.headers
    assert len(calls) == 1


def test_cached_ingress_rejects_runtime_live_key_injection():
    calls = []
    ingress = TestWebhookIngress(
        settings(),
        transport=httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(200)),
    )
    ingress.provider.key_id = "rzp_live_FORBIDDEN"
    with TestClient(ingress) as client:
        assert (
            client.post("/api/payments/webhook", content=RAW, headers=signed()).status_code == 503
        )
    assert calls == []


@pytest.mark.parametrize("flow", ["razorpay_test"], indirect=True)
def test_receipts_drop_card_banking_and_payer_data_but_preserve_exact_body_conflicts(flow):
    razorpay_flow(flow)
    entity = {
        "id": "rfnd_Minimized",
        "payment_id": "pay_fixture",
        "amount": 100,
        "currency": "INR",
        "status": "pending",
        "card": {"number": "synthetic-card"},
        "otp": "synthetic-otp",
        "upi_pin": "synthetic-pin",
        "banking_password": "synthetic-password",
        "email": "synthetic-payer@example.test",
        "notes": {"private": "synthetic-private"},
    }
    event = {
        "event": "refund.created",
        "payload": {"refund": {"entity": entity}},
        "private": "synthetic-top-level-private",
    }
    raw = json.dumps(event).encode()
    identifier = "evt_Minimized"
    response = flow["client"].post(
        "/api/payments/webhook", content=raw, headers=signed(raw, identifier)
    )
    assert response.status_code == 200
    with flow["factory"]() as db:
        receipt = db.get(ProcessedWebhook, identifier)
        assert receipt.payload_sha256 == hashlib.sha256(raw).hexdigest()
        assert json.loads(receipt.payload) == {
            "event": "refund.created",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_Minimized",
                        "payment_id": "pay_fixture",
                        "amount": 100,
                        "currency": "INR",
                        "status": "pending",
                    }
                }
            },
        }
        assert "synthetic-" not in receipt.payload
    assert (
        flow["client"]
        .post("/api/payments/webhook", content=raw, headers=signed(raw, identifier))
        .json()["duplicate"]
    )
    entity["otp"] = "changed-synthetic-value-not-retained"
    changed = json.dumps(event).encode()
    assert (
        flow["client"]
        .post("/api/payments/webhook", content=changed, headers=signed(changed, identifier))
        .status_code
        == 409
    )
    entity["status"] = {"unexpected": "synthetic-private"}
    malformed = json.dumps(event).encode()
    other_identifier = "evt_MinimizedMalformedMetadata"
    assert (
        flow["client"]
        .post(
            "/api/payments/webhook", content=malformed, headers=signed(malformed, other_identifier)
        )
        .status_code
        == 200
    )
    with flow["factory"]() as db:
        receipt = db.get(ProcessedWebhook, other_identifier)
        assert "status" not in json.loads(receipt.payload)["payload"]["refund"]["entity"]
        assert "synthetic-" not in receipt.payload


def test_proxy_limits_declared_and_streamed_bodies():
    calls = []
    with TestClient(
        TestWebhookIngress(
            settings(),
            transport=httpx.MockTransport(
                lambda request: calls.append(request) or httpx.Response(200)
            ),
        )
    ) as client:
        assert (
            client.post(
                "/api/payments/webhook", content=b"x" * 128001, headers=signed()
            ).status_code
            == 413
        )
        assert (
            client.post(
                "/api/payments/webhook",
                content=RAW,
                headers={**signed(), "content-length": "9" * 5000},
            ).status_code
            == 413
        )
        assert (
            client.post(
                "/api/payments/webhook",
                content=iter([b"x" * 64000, b"x" * 64001]),
                headers=signed(),
            ).status_code
            == 413
        )
    assert calls == []


def test_upstream_failures_and_redirects_are_not_followed():
    for outcome, status in ((302, 502), (503, 503)):
        calls = []

        def upstream(request):
            calls.append(request)
            return httpx.Response(outcome, headers={"Location": "https://attacker.invalid"})

        with TestClient(
            TestWebhookIngress(settings(), transport=httpx.MockTransport(upstream))
        ) as client:
            assert (
                client.post("/api/payments/webhook", content=RAW, headers=signed()).status_code
                == status
            )
        assert len(calls) == 1


@pytest.mark.parametrize("flow", ["razorpay_test"], indirect=True)
def test_refund_created_through_proxy_is_authenticated_deduplicated_and_informational(flow):
    razorpay_flow(flow)

    async def run():
        proxy = TestWebhookIngress(
            settings(), transport=httpx.ASGITransport(app=private_app, client=("127.0.0.1", 42123))
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=proxy), base_url="https://public.test"
        ) as client:
            first = await client.post("/api/payments/webhook", content=RAW, headers=signed())
            assert first.status_code == 200 and first.json() == {"received": True, "ignored": True}
            repeated = await client.post("/api/payments/webhook", content=RAW, headers=signed())
            assert repeated.status_code == 200 and repeated.json()["duplicate"] is True
            changed = RAW + b" "
            assert (
                await client.post("/api/payments/webhook", content=changed, headers=signed(changed))
            ).status_code == 409
            assert (
                await client.post("/api/payments/webhook", content=changed, headers=signed())
            ).status_code == 400
        await proxy.client.aclose()

    asyncio.run(run())
    with flow["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(ProcessedWebhook)) == 1
        receipt = db.get(ProcessedWebhook, "evt_ingress")
        assert receipt.status == "processed" and receipt.event_type == "refund.created"
        assert db.get(RentalBooking, flow["booking"]["id"]).payment_status == "unpaid"
        assert db.scalar(select(func.count()).select_from(JournalTransaction)) == 0
        assert db.scalar(select(func.count()).select_from(RefundIntent)) == 0


@pytest.mark.parametrize("flow", ["razorpay_test"], indirect=True)
@pytest.mark.parametrize("entity", [{}, {"id": "../invalid"}, [], "invalid"])
def test_refund_created_requires_a_valid_entity(flow, entity):
    razorpay_flow(flow)
    raw = json.dumps(
        {"event": "refund.created", "payload": {"refund": {"entity": entity}}}
    ).encode()
    assert (
        flow["client"].post("/api/payments/webhook", content=raw, headers=signed(raw)).status_code
        == 422
    )
    with flow["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(ProcessedWebhook)) == 0


@pytest.mark.parametrize("flow", ["razorpay_test"], indirect=True)
def test_order_paid_reconciles_an_authoritative_captured_payment(flow):
    _, _signature = razorpay_flow(flow)
    assert call(flow, "payments/create-order").status_code == 200
    provider = private_app.dependency_overrides[payment_provider]()
    original = provider.transport

    def transport(method, path, data, headers):
        if path == "orders/order_fixture/payments":
            return {
                "items": [{"id": "pay_fixture", "order_id": "order_fixture", "status": "captured"}]
            }
        return original(method, path, data, headers)

    provider.transport = transport
    raw = json.dumps(
        {"event": "order.paid", "payload": {"order": {"entity": {"id": "order_fixture"}}}}
    ).encode()
    assert (
        flow["client"].post("/api/payments/webhook", content=raw, headers=signed(raw)).status_code
        == 200
    )
    with flow["factory"]() as db:
        assert db.get(RentalBooking, flow["booking"]["id"]).payment_status == "captured"
    assert_balanced(flow)


@pytest.mark.parametrize("flow", ["razorpay_test"], indirect=True)
@pytest.mark.parametrize("terminal", ["processed", "failed"])
def test_refund_terminal_webhooks_only_reconcile_an_authorized_intent(flow, terminal):
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
    assert (
        flow["client"]
        .post(
            f"/api/borrow-requests/{flow['request_id']}/return/confirm",
            json={"approved": True},
            headers=flow["headers"]["lender"],
        )
        .status_code
        == 200
    )
    provider = private_app.dependency_overrides[payment_provider]()
    original, state, posts = provider.transport, {"status": "pending"}, []

    def transport(method, path, data, headers):
        if path == "payments/pay_fixture/refund" or path == "refunds/rfnd_TestTerminal":
            if method == "POST":
                posts.append(path)
            return {
                "id": "rfnd_TestTerminal",
                "payment_id": "pay_fixture",
                "amount": 50000,
                "currency": "INR",
                "status": state["status"],
            }
        return original(method, path, data, headers)

    provider.transport = transport
    pending = call(flow, "payments/refunds/execute", {"gateway_refund_approved": True})
    assert pending.status_code == 200 and pending.json()["refund"]["status"] == "pending"
    state["status"] = terminal
    raw = json.dumps(
        {
            "event": "refund." + terminal,
            "payload": {"refund": {"entity": {"id": "rfnd_TestTerminal"}}},
        }
    ).encode()
    for _ in range(2):
        assert (
            flow["client"]
            .post("/api/payments/webhook", content=raw, headers=signed(raw))
            .status_code
            == 200
        )
    with flow["factory"]() as db:
        refund = db.scalar(
            select(RefundIntent).where(RefundIntent.booking_id == flow["booking"]["id"])
        )
        assert refund.status == terminal
        assert db.get(RentalBooking, flow["booking"]["id"]).refunded_paise == (
            50000 if terminal == "processed" else 0
        )
    assert (
        len(posts) == 1
    )  # Synthetic initial dispatch only; callbacks never send another refund POST.
    assert_balanced(flow)
