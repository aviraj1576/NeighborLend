"""Verify the isolated webhook stack without revealing credentials or making payments."""

import argparse
import hashlib
import hmac
import json
import logging
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".payment-verification" / "webhook-ingress-20261110-01"
sys.path[:0] = [str(ROOT / ".test-tools"), str(ROOT)]


def main():
    import httpx
    from dotenv import dotenv_values

    from app.config import Settings
    from app.services.razorpay_service import configured_provider

    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--allow-public-test", action="store_true")
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    local = url.scheme == "http" and url.hostname == "127.0.0.1" and url.port == 8010
    public = (
        args.allow_public_test
        and url.scheme == "https"
        and url.port in (None, 443)
        and re.fullmatch(r"[a-z0-9-]+\.trycloudflare\.com", url.hostname or "")
    )
    if (
        not (local or public)
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in ("", "/")
    ):
        raise RuntimeError(
            "Only the local ingress or an explicitly supplied HTTPS Quick Tunnel origin is allowed"
        )
    config = Settings()
    if configured_provider(config).kind != "razorpay_test":
        raise RuntimeError("Razorpay Test credentials are required")
    state = json.loads((ARTIFACTS / "stack-state.json").read_text("utf-8"))
    database = Path(state["database"]).resolve()
    if (
        not state.get("isolated")
        or not database.is_relative_to(ARTIFACTS.resolve())
        or not database.is_file()
    ):
        raise RuntimeError("An isolated local stack is required")
    env_files = [path for path in (ROOT.parent / ".env", ROOT / ".env") if path.is_file()]
    before_hash = {path: hashlib.sha256(path.read_bytes()).digest() for path in env_files}
    checks = {}

    def require(name, condition):
        checks[name] = bool(condition)
        if not condition:
            raise RuntimeError(name)

    def counts():
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
            return {
                name: db.execute('SELECT COUNT(*) FROM "' + name + '"').fetchone()[0]
                for name in (
                    "users",
                    "rental_bookings",
                    "payment_transactions",
                    "refund_intents",
                    "journal_transactions",
                )
            }

    baseline = counts()
    identifier = "evt_ingresscheck_" + uuid4().hex
    raw = json.dumps(
        {
            "event": "refund.created",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_SyntheticIngressCheck",
                        "entity": "refund",
                        "status": "pending",
                    }
                }
            },
        },
        separators=(",", ":"),
    ).encode()
    key = config.razorpay_webhook_secret.get_secret_value().encode()

    def signed(body=raw):
        return {
            "x-razorpay-event-id": identifier,
            "x-razorpay-signature": hmac.new(key, body, hashlib.sha256).hexdigest(),
            "Content-Type": "application/json",
        }

    base = args.base_url.rstrip("/")
    with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
        response = client.post(base + "/api/payments/webhook", content=raw, headers=signed())
        require(
            "signed_delivery_accepted",
            response.status_code == 200 and response.json().get("ignored") is True,
        )
        repeated = client.post(base + "/api/payments/webhook", content=raw, headers=signed())
        require(
            "duplicate_event_is_idempotent",
            repeated.status_code == 200 and repeated.json().get("duplicate") is True,
        )
        require(
            "invalid_signature_rejected",
            client.post(
                base + "/api/payments/webhook",
                content=raw,
                headers={**signed(), "x-razorpay-signature": "0" * 64},
            ).status_code
            == 400,
        )
        require(
            "raw_body_tampering_rejected",
            client.post(
                base + "/api/payments/webhook", content=raw + b" ", headers=signed()
            ).status_code
            == 400,
        )
        require(
            "signed_event_id_conflict_rejected",
            client.post(
                base + "/api/payments/webhook", content=raw + b" ", headers=signed(raw + b" ")
            ).status_code
            == 409,
        )
        require(
            "missing_signature_rejected",
            client.post(base + "/api/payments/webhook", content=raw).status_code == 400,
        )
        require(
            "oversize_body_rejected",
            client.post(
                base + "/api/payments/webhook", content=b"x" * 128001, headers=signed()
            ).status_code
            == 413,
        )
        for path in (
            "/api/health",
            "/docs",
            "/openapi.json",
            "/api/payments/create-order",
            "/api/admin",
            "/uploads/file",
        ):
            require(
                "ingress_blocks_" + path.replace("/", "_"),
                client.get(base + path).status_code == 404,
            )
        require(
            "private_api_healthy_on_loopback",
            client.get("http://127.0.0.1:8001/api/health").status_code == 200,
        )
        for path in ("/api/health", "/docs", "/api/payments/webhook"):
            require(
                "private_api_rejects_public_host_" + path.replace("/", "_"),
                client.get(
                    "http://127.0.0.1:8001" + path,
                    headers={"Host": "public.example.test", "X-Forwarded-For": "203.0.113.1"},
                ).status_code
                == 403,
            )
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
        receipt = db.execute(
            "SELECT status, payload_sha256 FROM processed_webhooks WHERE event_id=?", (identifier,)
        ).fetchone()
        require(
            "durable_receipt_matches_exact_body",
            receipt == ("processed", hashlib.sha256(raw).hexdigest()),
        )
    require("no_user_or_financial_state_changes", counts() == baseline)
    require(
        "credential_files_unchanged",
        all(hashlib.sha256(p.read_bytes()).digest() == digest for p, digest in before_hash.items()),
    )
    require(
        "no_frontend_secret_variables",
        all(
            not (
                name.startswith("VITE_")
                and any(token in name for token in ("SECRET", "PASSWORD", "PRIVATE_KEY"))
            )
            for path in env_files
            for name in dotenv_values(path)
        ),
    )
    result = {
        "result": "PASS",
        "scope": "public_tunnel" if public else "local_tcp",
        "checks": checks,
        "local_secret_consistency": "PASS",
        "dashboard_secret_consistency": "NOT_VERIFIED",
        "cloudflare_started": False,
        "checkout_or_refund_performed": False,
        "existing_user_database_accessed": False,
    }
    (ARTIFACTS / ("public-verification.json" if public else "local-verification.json")).write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "result": "FAIL",
                    "error_type": type(exc).__name__,
                    "details": "Sensitive exception text withheld; no credentials were printed",
                }
            )
        )
        raise SystemExit(1) from None
