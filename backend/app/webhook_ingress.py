"""Loopback reverse proxy exposing only the test-mode Razorpay webhook.

Run with uvicorn app.webhook_ingress:create_app --factory --host 127.0.0.1
--port 8010 --no-proxy-headers --no-access-log. The private API stays on port 8001.
No application database, admin routes, docs, uploads or AI are imported here.
"""

import asyncio

import httpx

from app.config import get_settings
from app.services.razorpay_service import (
    WEBHOOK_MAX_BODY_BYTES,
    ProviderError,
    configured_provider,
)

WEBHOOK_PATH = b"/api/payments/webhook"
UPSTREAM = "http://127.0.0.1:8001/api/payments/webhook"


class TestWebhookIngress:
    __test__ = False

    def __init__(self, settings, *, transport=None):
        if (
            settings.app_env.lower() not in {"development", "test"}
            or settings.deployment_exposure != "local"
            or settings.payment_provider != "razorpay_test"
        ):
            raise ProviderError("ingress_requires_local_test_configuration")
        self.provider = configured_provider(settings)
        self.client = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(20, connect=3, pool=3),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
            follow_redirects=False,
            trust_env=False,
        )

    @staticmethod
    async def respond(send, status, body):
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await self.client.aclose()
                    await send({"type": "lifespan.shutdown.complete"})
                    return
            return
        if scope["type"] != "http":
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            return
        if (
            scope.get("raw_path", scope["path"].encode()) != WEBHOOK_PATH
            or scope["path"] != WEBHOOK_PATH.decode()
            or scope["method"] != "POST"
            or scope.get("query_string")
        ):
            await self.respond(send, 404, b'{"detail":"Not found"}')
            return
        headers = scope.get("headers", [])

        def values(name):
            return [v for k, v in headers if k.lower() == name]

        signatures, identifiers = values(b"x-razorpay-signature"), values(b"x-razorpay-event-id")
        encodings = values(b"content-encoding")
        if (
            len(signatures) != 1
            or len(identifiers) != 1
            or not identifiers[0]
            or len(identifiers[0]) > 128
            or any(c < 33 or c > 126 for c in identifiers[0])
            or encodings
            and encodings != [b"identity"]
        ):
            await self.respond(send, 400, b'{"detail":"Invalid webhook authentication"}')
            return
        lengths = values(b"content-length")
        if lengths and (len(lengths) != 1 or not lengths[0].isdigit()):
            await self.respond(send, 400, b'{"detail":"Invalid content length"}')
            return
        normalized_length = (lengths[0].lstrip(b"0") or b"0") if lengths else b"0"
        if lengths and (
            len(normalized_length) > 6 or int(normalized_length) > WEBHOOK_MAX_BODY_BYTES
        ):
            await self.respond(send, 413, b'{"detail":"Webhook too large"}')
            return
        raw = bytearray()
        try:
            async with asyncio.timeout(10):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(raw) + len(chunk) > WEBHOOK_MAX_BODY_BYTES:
                        await self.respond(send, 413, b'{"detail":"Webhook too large"}')
                        return
                    raw.extend(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await self.respond(send, 408, b'{"detail":"Webhook body timeout"}')
            return
        raw = bytes(raw)
        if lengths and int(normalized_length) != len(raw):
            await self.respond(send, 400, b'{"detail":"Content length mismatch"}')
            return
        signature = signatures[0].decode("ascii", errors="replace")
        try:
            authenticated = self.provider.verify_webhook(raw, signature)
        except ProviderError:
            await self.respond(send, 503, b'{"detail":"Sandbox configuration unavailable"}')
            return
        if not authenticated:
            await self.respond(send, 400, b'{"detail":"Invalid webhook signature"}')
            return
        # Never forward caller-supplied Host, authorization, cookies or proxy headers.
        # The fixed loopback target still applies its own raw-body HMAC verification.
        forwarded = {
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": identifiers[0].decode("ascii"),
        }
        try:
            async with self.client.stream(
                "POST", UPSTREAM, content=raw, headers=forwarded
            ) as response:
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > 65_536:
                        raise ValueError("upstream_response_limit")
                    body.extend(chunk)
                status = response.status_code
        except (httpx.HTTPError, ValueError):
            await self.respond(send, 503, b'{"detail":"Webhook backend unavailable"}')
            return
        if 300 <= status < 400:
            await self.respond(send, 502, b'{"detail":"Unexpected backend redirect"}')
            return
        await self.respond(send, status, bytes(body))


def create_app():
    return TestWebhookIngress(get_settings())
