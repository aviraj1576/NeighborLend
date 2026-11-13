"""Prepare two isolated unpaid Test bookings; never checkout, refund, or deduct.

Uses only the existing validated local webhook stack database. Existing rows and
credential files are fingerprinted before work and verified afterwards. New demo
credentials stay in ignored local artifacts and are never printed.
"""

import argparse
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / ".payment-verification/webhook-ingress-20261110-01"
OUTPUT = ROOT / ".payment-verification/finalization-20261111"
sys.path[:0] = [str(ROOT / ".test-tools"), str(ROOT)]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def save(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def fingerprints(database):
    tables = {}
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            if not name.startswith("sqlite_"):
                quoted = '"' + name.replace('"', '""') + '"'
                tables[name] = sorted(
                    hashlib.sha256(repr(tuple(row)).encode()).hexdigest()
                    for row in db.execute("SELECT * FROM " + quoted)
                )
        require(not db.execute("PRAGMA foreign_key_check").fetchall(), "Foreign key integrity")
    credentials = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT.parent / ".env", ROOT / ".env", STACK / "checkout-accounts.json")
        if p.is_file()
    }
    return {"tables": tables, "credentials": credentials}


def main():
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prepare", action="store_true", help="Create new local fixtures and Test orders"
    )
    args = parser.parse_args()
    stack = json.loads((STACK / "stack-state.json").read_text("utf-8"))
    database = Path(stack["database"]).resolve()
    require(
        stack.get("isolated") and database.is_relative_to(STACK.resolve()) and database.is_file(),
        "Existing isolated stack required",
    )
    os.environ.update(
        DATABASE_URL="sqlite:///" + database.as_posix(), APP_ENV="test", AUTO_MIGRATE="false"
    )
    from app.config import get_settings
    from app.services.razorpay_service import configured_provider

    config = get_settings()
    provider = configured_provider(config)
    require(
        provider.kind == "razorpay_test"
        and provider.sandbox_only
        and config.deployment_exposure == "local",
        "Local Test configuration required",
    )
    OUTPUT.mkdir(exist_ok=True, parents=True)
    baseline_path = OUTPUT / "preservation-baseline.json"
    if not baseline_path.exists():
        require(args.prepare, "Run --prepare to establish the original-row baseline")
        save(baseline_path, fingerprints(database))
    baseline = json.loads(baseline_path.read_text("utf-8"))
    state_path, accounts_path = OUTPUT / "scenarios.json", OUTPUT / "scenario-accounts.json"
    state = (
        json.loads(state_path.read_text("utf-8"))
        if state_path.exists()
        else {"database": str(database), "scenarios": {}}
    )
    require(state["database"] == str(database), "Scenario database changed")
    if args.prepare:
        # Only new fixture identities/listings are seeded directly. Agreements,
        # authorization, snapshots and orders use the authenticated application.
        import httpx

        from app.database import SessionLocal, engine
        from app.models import Listing, ListingStatus, User
        from app.services.auth import hash_password

        require(Path(engine.url.database).resolve() == database, "Database mismatch")
        if not accounts_path.exists():
            accounts = {"database": str(database), "test_only": True}
            suffix = uuid4().hex[:10]
            for role in ("borrower", "lender", "admin"):
                accounts[role] = {
                    "id": str(uuid4()),
                    "username": f"lifecycle_{role}_{suffix}",
                    "email": f"lifecycle-{role}-{suffix}@example.test",
                    "password": secrets.token_urlsafe(24),
                }
            save(accounts_path, accounts)
        accounts = json.loads(accounts_path.read_text("utf-8"))
        require(accounts["database"] == str(database), "Account database mismatch")
        with SessionLocal() as db:
            for role in ("borrower", "lender", "admin"):
                account = accounts[role]
                if not db.get(User, account["id"]):
                    db.add(
                        User(
                            id=account["id"],
                            name="Lifecycle Test " + role.title(),
                            username=account["username"],
                            email=account["email"],
                            password_hash=hash_password(account["password"]),
                            is_verified=True,
                            is_admin=role == "admin",
                        )
                    )
            db.commit()
        with httpx.Client(
            base_url="http://127.0.0.1:8001/api",
            timeout=40,
            trust_env=False,
            follow_redirects=False,
        ) as client:
            tokens = {}

            def call(method, path, role, data=None):
                headers = {"Authorization": "Bearer " + tokens[role]} if role else {}
                response = client.request(method, path, json=data, headers=headers)
                require(response.status_code == 200, f"API {response.status_code}: {path}")
                return response.json()

            for role in ("borrower", "lender"):
                result = call(
                    "POST",
                    "/auth/login",
                    None,
                    {
                        "username_or_email": accounts[role]["username"],
                        "password": accounts[role]["password"],
                    },
                )
                tokens[role] = result["access_token"]
                require(
                    call("GET", "/auth/me", role)["id"] == accounts[role]["id"], "Identity mismatch"
                )
            for name, deduction in (("A", 0), ("B", 60000)):
                row = state["scenarios"].setdefault(
                    name,
                    {
                        "listing_id": str(uuid4()),
                        "expected_refund_paise": 200000 - deduction,
                        "proposed_deduction_paise": deduction,
                    },
                )
                save(state_path, state)
                with SessionLocal() as db:
                    if not db.get(Listing, row["listing_id"]):
                        db.add(
                            Listing(
                                id=row["listing_id"],
                                owner_id=accounts["lender"]["id"],
                                name=f"Lifecycle TEST scenario {name}",
                                category="Other",
                                description="Isolated rental fixture. No real item or money.",
                                price_per_day=500,
                                min_price_per_day=500,
                                security_deposit=2000,
                                status=ListingStatus.published,
                            )
                        )
                        db.commit()
                if "conversation_id" not in row:
                    row["conversation_id"] = call(
                        "POST",
                        "/conversations",
                        "borrower",
                        {"lender_id": accounts["lender"]["id"]},
                    )["id"]
                    save(state_path, state)
                offers_path = "/conversations/" + row["conversation_id"] + "/offers"
                offers = call("GET", offers_path, "borrower")
                matches = [o for o in offers if o["listing_id"] == row["listing_id"]]
                require(len(matches) <= 1, "Ambiguous scenario offers")
                if matches:
                    offer = matches[0]
                else:
                    start = (datetime.utcnow() + timedelta(days=1)).replace(microsecond=0)
                    offer = call(
                        "POST",
                        offers_path,
                        "borrower",
                        {
                            "listing_id": row["listing_id"],
                            "daily_price": 500,
                            "start_date": start.isoformat(),
                            "end_date": (start + timedelta(days=1)).isoformat(),
                            "message": f"Authorized isolated Test scenario {name}; deduction still requires independent human review.",
                        },
                    )
                if offer["status"] == "pending":
                    offer = call("POST", "/offers/" + offer["id"] + "/accept", "lender")
                require(offer["status"] == "accepted", "Accepted agreement required")
                row.update(offer_id=offer["id"], request_id=offer["borrow_request_id"])
                save(state_path, state)
                booking = call("GET", "/payments/by-request/" + row["request_id"], "borrower")
                require(
                    (
                        booking["rental_fee_paise"],
                        booking["security_deposit_paise"],
                        booking["total_amount_paise"],
                        booking["provider"],
                    )
                    == (50000, 200000, 250000, "razorpay_test"),
                    "Financial snapshot mismatch",
                )
                row.update(
                    booking_id=booking["id"],
                    amount_paise=250000,
                    currency="INR",
                    checkout_url="http://127.0.0.1:5175/borrow-requests/" + row["request_id"],
                )
                save(state_path, state)
                if booking["payment_status"] != "captured":
                    order = call(
                        "POST", "/payments/create-order", "borrower", {"booking_id": booking["id"]}
                    )
                    require(
                        order["amount_paise"] == 250000 and order["sandbox_only"] is True,
                        "Sandbox order mismatch",
                    )
                    row["order_id"] = order["order_id"]
                    official = provider.fetch_order(order["order_id"])
                    require(
                        official["amount"] == 250000
                        and official["currency"] == "INR"
                        and official["notes"]["booking_id"] == booking["id"],
                        "Provider association mismatch",
                    )
                    row["provider_status"] = official["status"]
                row["manual_checkout"] = (
                    "complete" if booking["payment_status"] == "captured" else "pending"
                )
                row["persistent_deduction_authorized"] = False
                save(state_path, state)
        engine.dispose()
    after = fingerprints(database)
    preserved = all(
        not (Counter(rows) - Counter(after["tables"].get(table, [])))
        for table, rows in baseline["tables"].items()
    )
    report = {
        "all_original_rows_preserved": preserved,
        "original_credential_files_preserved": baseline["credentials"] == after["credentials"],
        "scenarios": state["scenarios"],
        "gateway_refund_posts": 0,
        "deductions_applied": 0,
        "checkout_completed_by_script": False,
    }
    save(OUTPUT / "scenario-verification.json", report)
    require(
        preserved and report["original_credential_files_preserved"], "Preservation check failed"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Suppress tracebacks/provider responses that could expose private values.
        print(
            "Scenario preparation stopped: "
            + (str(exc) if type(exc) is RuntimeError else type(exc).__name__),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
