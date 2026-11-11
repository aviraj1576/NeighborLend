import hashlib
import hmac

import pytest

from app.config import Settings
from app.services.razorpay_service import ProviderError, RazorpayTestProvider, configured_provider


def config(**values):
    values.setdefault(
        "payment_provider",
        "razorpay_test" if any(name.startswith("razorpay_") for name in values) else "mock",
    )
    values.setdefault("payment_demo_mode", values["payment_provider"] == "mock")
    return Settings(_env_file=None, app_env="test", **values)


def test_default_mock_needs_explicit_demo_and_never_falls_back():
    with pytest.raises(ProviderError):
        configured_provider(config(payment_demo_mode=False))
    assert configured_provider(config(payment_demo_mode=True)).kind == "mock"
    for values in (
        {"razorpay_key_id": "rzp_live_fake"},
        {},
        {"razorpay_key_id": "rzp_test_fake", "razorpay_key_secret": ""},
    ):
        with pytest.raises(ProviderError):
            configured_provider(config(payment_provider="razorpay_test", **values))
    with pytest.raises(ProviderError):
        configured_provider(Settings(_env_file=None, app_env="production", payment_demo_mode=True))


def test_hmac_uses_stored_order_and_constant_time_comparison():
    provider = RazorpayTestProvider(
        config(
            razorpay_key_id="rzp_test_fixture",
            razorpay_key_secret="synthetic-secret",
            razorpay_webhook_secret="synthetic-webhook",
        )
    )
    signature = hmac.new(
        b"synthetic-secret", b"order_fixture|pay_fixture", hashlib.sha256
    ).hexdigest()
    assert provider.verify_checkout("order_fixture", "pay_fixture", signature)
    assert not provider.verify_checkout("order_other", "pay_fixture", signature)
    raw = b'{"event":"payment.captured"}'
    digest = hmac.new(b"synthetic-webhook", raw, hashlib.sha256).hexdigest()
    assert provider.verify_webhook(raw, digest)
    assert not provider.verify_webhook(raw + b" ", digest)


def test_official_refund_idempotency_header_and_fixed_path():
    calls = []

    def transport(method, path, data, headers):
        calls.append((method, path, data, headers))
        return {"status": "pending"}

    provider = RazorpayTestProvider(
        config(
            razorpay_key_id="rzp_test_fixture",
            razorpay_key_secret="synthetic-secret",
            razorpay_webhook_secret="synthetic-webhook",
        ),
        transport,
    )
    for _ in range(2):
        provider.refund("pay_fixture", 50000, "unique-refund-reference")
    assert calls[0] == calls[1]
    assert calls[0][1] == "payments/pay_fixture/refund"
    assert calls[0][3]["X-Refund-Idempotency"] == "unique-refund-reference"
    for invalid in ("../other", "https://attacker.invalid", "pay_fixture?key=secret"):
        with pytest.raises(ProviderError):
            provider.fetch_payment(invalid)
    assert not provider.verify_checkout("order_fixture", "pay_fixture", "🙂" * 64)
