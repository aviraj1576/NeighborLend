"""Test-only providers. Standard-library HTTPS avoids adding an SDK dependency."""

import base64
import hashlib
import hmac
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

WEBHOOK_MAX_BODY_BYTES = 128_000
MAX_AMOUNT_PAISE = 1_000_000_000
TEST_KEY = re.compile(r"rzp_test_[A-Za-z0-9]+")


class ProviderError(Exception):
    def __init__(self, code="provider_unavailable", *, definite=False):
        self.code = code
        self.definite = definite
        super().__init__(code)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class DisabledPaymentProvider:
    kind = "disabled"
    key_id = None

    def __init__(self, settings=None):
        self._settings = settings

    @property
    def sandbox_only(self):
        if self._settings is not None:
            validate_payment_configuration(self._settings)
            if self._settings.payment_provider != "disabled":
                raise ProviderError("conflicting_payment_modes")
        return self.kind == "disabled"


def validate_payment_configuration(settings):
    from urllib.parse import urlparse

    if settings.payment_provider not in {"disabled", "mock", "razorpay_test"}:
        raise ProviderError("invalid_payment_provider")
    if settings.deployment_exposure not in {"local", "public"}:
        raise ProviderError("invalid_deployment_exposure")
    public = settings.deployment_exposure == "public" or settings.app_env.lower() in {
        "prod",
        "production",
    }
    if not public:
        for url in [settings.public_base_url, *settings.cors_origin_list]:
            if url and urlparse(url).hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ProviderError("local_deployment_requires_loopback_urls")
    if public and (
        len(settings.jwt_secret) < 32
        or settings.jwt_secret == "neighborlend-super-secret-key-2026-prototype"
        or settings.jwt_secret.lower().startswith(("change-me", "changeme", "your-secret"))
        or len(set(settings.jwt_secret)) < 12
    ):
        raise ProviderError("private_strong_jwt_secret_required")
    # Reject live credentials even if the currently selected provider is disabled.
    if settings.razorpay_key_id and (
        not isinstance(settings.razorpay_key_id, str)
        or not TEST_KEY.fullmatch(settings.razorpay_key_id)
    ):
        raise ProviderError("only_test_keys_allowed")
    credentials = (
        settings.razorpay_key_id,
        settings.razorpay_key_secret.get_secret_value(),
        settings.razorpay_webhook_secret.get_secret_value(),
    )
    if any(credentials) and not all(value and value == value.strip() for value in credentials):
        raise ProviderError("test_credentials_required")
    if settings.payment_provider == "razorpay_test":
        if not all(credentials):
            raise ProviderError("test_credentials_required")
        if settings.payment_demo_mode:
            raise ProviderError("conflicting_payment_modes")
    if settings.payment_provider == "mock":
        if any(credentials):
            raise ProviderError("conflicting_payment_modes")
        if not settings.payment_demo_mode:
            raise ProviderError("explicit_demo_mode_required")
    if settings.payment_provider == "mock" and public:
        raise ProviderError("mock_requires_isolated_loopback_deployment")
    return public


class MockPaymentProvider:
    kind = "mock"
    key_id = None

    def __init__(self, settings=None):
        if settings is None:
            from app.config import get_settings

            settings = get_settings()
        self._settings = settings

    @property
    def sandbox_only(self):
        if self.kind != "mock":
            raise ProviderError("invalid_payment_provider")
        if self._settings is not None:
            validate_payment_configuration(self._settings)
            if self._settings.payment_provider != "mock":
                raise ProviderError("conflicting_payment_modes")
        return True

    def create_order(self, booking, reference):
        self.sandbox_only
        return {
            "id": "order_mock_" + reference,
            "receipt": reference,
            "amount": booking.total_amount_paise,
            "currency": "INR",
            "status": "created",
        }

    def fetch_order(self, order):
        self.sandbox_only
        return dict(order)

    def fetch_payment(self, payment):
        self.sandbox_only
        return dict(payment)

    def demo_payment(self, order, outcome, attempt):
        self.sandbox_only
        return {
            "id": "pay_mock_" + attempt,
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": "INR",
            "status": {
                "success": "captured",
                "failed": "failed",
                "cancelled": "failed",
                "pending": "authorized",
            }[outcome],
        }

    def refund(self, payment_id, amount, reference):
        self.sandbox_only
        return {
            "id": "rfnd_mock_" + reference,
            "payment_id": payment_id,
            "amount": amount,
            "currency": "INR",
            "status": "processed",
        }

    def fetch_refund(self, refund):
        self.sandbox_only
        return dict(refund)

    def verify_checkout(self, *args):
        self.sandbox_only
        raise ProviderError("mock_uses_explicit_demo_confirmation")

    def verify_webhook(self, *args):
        self.sandbox_only
        return False


class RazorpayTestProvider:
    kind = "razorpay_test"

    def __init__(self, settings, transport=None):
        validate_payment_configuration(settings)
        if (
            settings.payment_provider != self.kind
            or not TEST_KEY.fullmatch(settings.razorpay_key_id)
            or not settings.razorpay_key_secret
            or not settings.razorpay_key_secret.get_secret_value().strip()
            or not settings.razorpay_webhook_secret
            or not settings.razorpay_webhook_secret.get_secret_value().strip()
        ):
            raise ProviderError("test_credentials_required")
        self.key_id = settings.razorpay_key_id
        self._secret = settings.razorpay_key_secret.get_secret_value()
        self._webhook = settings.razorpay_webhook_secret.get_secret_value()
        self._settings = settings
        self.transport = transport

    @property
    def sandbox_only(self):
        # Revalidate the cached adapter AND its source configuration before every
        # dispatch or HMAC operation. A mutated live key never reaches transport.
        validate_payment_configuration(self._settings)
        if (
            self.kind != "razorpay_test"
            or self._settings.payment_provider != "razorpay_test"
            or not isinstance(self.key_id, str)
            or not TEST_KEY.fullmatch(self.key_id)
            or self.key_id != self._settings.razorpay_key_id
            or not isinstance(self._secret, str)
            or not isinstance(self._webhook, str)
            or not hmac.compare_digest(
                self._secret.encode(),
                self._settings.razorpay_key_secret.get_secret_value().encode(),
            )
            or not hmac.compare_digest(
                self._webhook.encode(),
                self._settings.razorpay_webhook_secret.get_secret_value().encode(),
            )
        ):
            raise ProviderError("test_credentials_required")
        return True

    @staticmethod
    def amount(value):
        if type(value) is not int or not 0 < value <= MAX_AMOUNT_PAISE:
            raise ProviderError("invalid_provider_amount")
        return value

    @staticmethod
    def allowed_operation(method, path, payload):
        # This adapter has no capture, payout, transfer, account or settlement
        # endpoint. Reject unsupported paths even when called from Python code.
        if (
            method == "GET"
            and payload is None
            and (
                re.fullmatch(r"orders/order_[A-Za-z0-9]+(?:/payments)?", path)
                or re.fullmatch(r"payments/pay_[A-Za-z0-9]+", path)
                or re.fullmatch(r"refunds/rfnd_[A-Za-z0-9]+", path)
                or re.fullmatch(r"payments/pay_[A-Za-z0-9]+/refunds\?count=100&skip=\d+", path)
                or re.fullmatch(r"orders\?receipt=[A-Za-z0-9-]{1,128}&count=100", path)
            )
        ):
            return
        if method == "POST" and isinstance(payload, dict):
            if path == "orders" and set(payload) == {"amount", "currency", "receipt", "notes"}:
                RazorpayTestProvider.amount(payload["amount"])
                if (
                    payload["currency"] == "INR"
                    and isinstance(payload["notes"], dict)
                    and set(payload["notes"]) == {"booking_id"}
                ):
                    return
            if re.fullmatch(r"payments/pay_[A-Za-z0-9]+/refund", path) and set(payload) == {
                "amount",
                "speed",
                "receipt",
            }:
                RazorpayTestProvider.amount(payload["amount"])
                if payload["speed"] == "normal":
                    return
        raise ProviderError("unsupported_provider_operation")

    def _request(self, method, path, payload=None, idempotency=None):
        key_id, secret = self.key_id, self._secret
        self.sandbox_only
        if not isinstance(key_id, str) or not TEST_KEY.fullmatch(key_id):
            raise ProviderError("only_test_keys_allowed")
        self.allowed_operation(method, path, payload)
        # Host is fixed; identifiers below are allowlisted. No automatic POST retries.
        token = base64.b64encode(f"{key_id}:{secret}".encode()).decode()
        headers = {
            "Authorization": "Basic " + token,
            "Content-Type": "application/json",
            "Accept-Encoding": "identity",
        }
        if idempotency:
            headers["X-Refund-Idempotency"] = idempotency
        if self.transport is not None:
            result = self.transport(method, path, payload, headers)
            return self.response(result)
        request = Request(
            "https://api.razorpay.com/v1/" + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=15) as response:
                if response.headers.get("Content-Encoding", "identity") != "identity":
                    raise ProviderError("invalid_provider_response")
                data = response.read(1_000_001)
                if len(data) > 1_000_000:
                    raise ProviderError("provider_response_limit")
                result = json.loads(data)
                return self.response(result)
        except HTTPError as exc:
            # Validation/authentication rejection cannot have created an order.
            if exc.code in {400, 401, 403, 404, 422}:
                raise ProviderError("provider_request_rejected", definite=True) from None
            raise ProviderError("provider_outcome_unknown") from None
        except (URLError, TimeoutError, ValueError, OSError):
            raise ProviderError("provider_outcome_unknown") from None

    @staticmethod
    def response(result):
        if not isinstance(result, dict):
            raise ProviderError("invalid_provider_response")
        if result.get("livemode") is True or (
            isinstance(result.get("items"), list)
            and any(
                isinstance(row, dict) and row.get("livemode") is True for row in result["items"]
            )
        ):
            raise ProviderError("live_provider_response_forbidden")
        return result

    @staticmethod
    def identifier(value, prefix=None):
        if (
            not isinstance(value, str)
            or not re.fullmatch(r"(?:order|pay|rfnd)_[A-Za-z0-9]+", value)
            or (prefix is not None and not value.startswith(prefix + "_"))
        ):
            raise ProviderError("invalid_provider_identifier")
        return value

    @staticmethod
    def collection(data):
        items = data.get("items")
        if (
            not isinstance(items, list)
            or len(items) > 100
            or any(not isinstance(row, dict) for row in items)
        ):
            raise ProviderError("invalid_provider_response")
        return items

    def create_order(self, booking, reference):
        return self._request(
            "POST",
            "orders",
            {
                "amount": booking.total_amount_paise,
                "currency": "INR",
                "receipt": reference,
                "notes": {"booking_id": booking.id},
            },
        )

    def find_order(self, reference):
        data = self._request("GET", "orders?" + urlencode({"receipt": reference, "count": 100}))
        items = [row for row in self.collection(data) if row.get("receipt") == reference]
        if len(items) != 1:
            raise ProviderError("order_reconciliation_required")
        return items[0]

    def fetch_order(self, order_id):
        return self._request("GET", "orders/" + self.identifier(order_id, "order"))

    def order_payments(self, order_id):
        return self.collection(
            self._request("GET", "orders/" + self.identifier(order_id, "order") + "/payments")
        )

    def fetch_payment(self, payment_id):
        return self._request("GET", "payments/" + self.identifier(payment_id, "pay"))

    def verify_checkout(self, order_id, payment_id, signature):
        self.sandbox_only
        expected = hmac.new(
            self._secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
        ).hexdigest()
        return (
            isinstance(signature, str)
            and bool(re.fullmatch(r"[a-f0-9]{64}", signature))
            and hmac.compare_digest(expected, signature)
        )

    def verify_webhook(self, raw, signature):
        self.sandbox_only
        expected = hmac.new(self._webhook.encode(), raw, hashlib.sha256).hexdigest()
        return (
            isinstance(signature, str)
            and bool(re.fullmatch(r"[a-f0-9]{64}", signature))
            and hmac.compare_digest(expected, signature)
        )

    def refund(self, payment_id, amount, reference):
        return self._request(
            "POST",
            "payments/" + self.identifier(payment_id, "pay") + "/refund",
            {"amount": amount, "speed": "normal", "receipt": reference},
            reference,
        )

    def fetch_refund(self, refund_id):
        return self._request("GET", "refunds/" + self.identifier(refund_id, "rfnd"))

    def find_refund(self, payment_id, reference):
        """Recover a lost POST response using GETs and its immutable receipt."""
        payment_id = self.identifier(payment_id, "pay")
        matches = []
        for skip in range(0, 1000, 100):
            rows = self.collection(
                self._request("GET", f"payments/{payment_id}/refunds?count=100&skip={skip}")
            )
            matches.extend(row for row in rows if row.get("receipt") == reference)
            if len(rows) < 100:
                if len(matches) == 1:
                    return matches[0]
                break
        raise ProviderError("refund_reconciliation_required")


def configured_provider(settings):
    validate_payment_configuration(settings)
    if settings.payment_provider == "disabled":
        return DisabledPaymentProvider(settings)
    if settings.payment_provider == "mock":
        if not settings.payment_demo_mode:
            raise ProviderError("explicit_demo_mode_required")
        return MockPaymentProvider(settings)
    if settings.payment_provider == "razorpay_test":
        return RazorpayTestProvider(settings)
    raise ProviderError("invalid_payment_provider")
