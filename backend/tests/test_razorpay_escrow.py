"""Authenticated payment/rental integration; isolated SQLite and synthetic gateway data."""

import hashlib
import hmac
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import Base, get_db
from app.main import app
from app.models import Conversation, Listing, ListingStatus, NegotiationOffer, OfferStatus, User
from app.payment_models import (
    EscrowLedgerEntry,
    JournalTransaction,
    RentalBooking,
)
from app.routers.payments import payment_provider
from app.services.auth import create_access_token
from app.services.payment_migrations import migrate_payments
from app.services.payments import PaymentService
from app.services.razorpay_service import MockPaymentProvider, ProviderError, RazorpayTestProvider


def test_anonymous_and_cross_rental_financial_reads_are_denied(flow):
    route = f"/api/payments/bookings/{flow['booking']['id']}"
    assert flow["client"].get(route).status_code == 401
    assert flow["client"].get(route, headers=flow["headers"]["other"]).status_code == 403
    assert (
        flow["client"]
        .post("/api/payments/create-order", json={"booking_id": flow["booking"]["id"]})
        .status_code
        == 401
    )


@pytest.mark.parametrize("flow", ["expired"], indirect=True)
def test_expired_booking_cannot_create_payment_order(flow):
    result = call(flow, "payments/create-order")
    assert result.status_code == 409
    assert "expired" in result.json()["detail"]
    assert (
        flow["client"]
        .get(f"/api/payments/by-request/{flow['request_id']}", headers=flow["headers"]["borrower"])
        .headers["cache-control"]
        == "no-store"
    )
    with flow["factory"]() as db:
        from app.payment_models import PaymentTransaction

        assert db.scalar(select(PaymentTransaction)) is None


@pytest.fixture
def flow(tmp_path, monkeypatch, request):
    realistic = getattr(request, "param", "mock") == "realistic"
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "rental_evidence_dir", str(tmp_path / "evidence"))
    if getattr(request, "param", "mock") == "razorpay_test":
        from types import SimpleNamespace

        monkeypatch.setattr(
            "app.services.razorpay_service.configured_provider",
            lambda settings: SimpleNamespace(kind="razorpay_test"),
        )
    postgres_root, schema = None, None
    if getattr(request, "param", "mock") == "postgres":
        from sqlalchemy.engine import make_url

        url = os.environ.get("PAYMENT_TEST_POSTGRES_URL")
        if not url:
            pytest.skip(
                "No isolated local PostgreSQL service configured (PAYMENT_TEST_POSTGRES_URL)"
            )
        parsed = make_url(url)
        if parsed.host not in {"127.0.0.1", "localhost"} or not (parsed.database or "").startswith(
            "neighborlend_test_"
        ):
            pytest.fail("PostgreSQL tests require a dedicated local neighborlend_test_* database")
        schema = "payment_test_" + uuid4().hex
        postgres_root = create_engine(url)
        with postgres_root.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_engine(url, connect_args={"options": "-csearch_path=" + schema})
    else:
        engine = create_engine(
            f"sqlite:///{(tmp_path / 'financial.db').as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 15},
        )

        @event.listens_for(engine, "connect")
        def fk(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    migrate_payments(engine)
    migrate_payments(engine)  # Additive migration is repeatable.
    factory = sessionmaker(bind=engine)
    with factory() as db:
        users = {}
        for role in ("lender", "borrower", "other", "admin"):
            user = User(
                id=str(uuid4()),
                name=role,
                username=role,
                email=f"{role}@example.test",
                password_hash="unused",
                is_verified=True,
                is_admin=role == "admin",
            )
            db.add(user)
            users[role] = user
        db.flush()
        listing = Listing(
            id=str(uuid4()),
            owner_id=users["lender"].id,
            name="Synthetic drill",
            category="Tools",
            price_per_day=500 if realistic else 200,
            security_deposit=2000 if realistic else 500,
            status=ListingStatus.published,
        )
        db.add(listing)
        db.flush()
        conv = Conversation(borrower_id=users["borrower"].id, lender_id=users["lender"].id)
        db.add(conv)
        db.flush()
        offer = NegotiationOffer(
            conversation_id=conv.id,
            listing_id=listing.id,
            sender_id=users["borrower"].id,
            daily_price=500 if realistic else 200,
            total_cost=500 if realistic else 400,
            start_date=datetime.utcnow()
            + timedelta(days=-3 if getattr(request, "param", "mock") == "expired" else 1),
            end_date=datetime.utcnow()
            + timedelta(
                days=-1 if getattr(request, "param", "mock") == "expired" else 2 if realistic else 3
            ),
            status=OfferStatus.pending,
        )
        from app.services.negotiation import snapshot_offer_terms

        snapshot_offer_terms(offer, listing, conv)
        db.add(offer)
        db.commit()
        headers = {
            name: {"Authorization": "Bearer " + create_access_token(user.id)}
            for name, user in users.items()
        }
        ids = {name: user.id for name, user in users.items()}
        oid = offer.id

    def dependency():
        with factory() as db:
            yield db

    provider = MockPaymentProvider()
    old = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = dependency
    app.dependency_overrides[payment_provider] = lambda: provider
    with TestClient(app) as client:
        response = client.post(f"/api/offers/{oid}/accept", headers=headers["lender"])
        assert response.status_code == 200, response.text
        request_id = response.json()["borrow_request_id"]
        booking = client.get(
            f"/api/payments/by-request/{request_id}", headers=headers["borrower"]
        ).json()
        yield {
            "client": client,
            "headers": headers,
            "ids": ids,
            "booking": booking,
            "request_id": request_id,
            "factory": factory,
            "provider": provider,
        }
    app.dependency_overrides.clear()
    app.dependency_overrides.update(old)
    engine.dispose()
    if postgres_root:
        # Only the UUID schema created by this fixture is removed, never user tables.
        with postgres_root.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        postgres_root.dispose()


def call(flow, path, data=None, role=None):
    # Positive refund-operation fixtures use the administrator required by policy.
    # Authorization-denial tests always supply their actor explicitly.
    if role is None:
        role = "admin" if path in {"payments/refunds/execute", "payments/refunds/reconcile"} else "borrower"
    if path == "disputes/respond" and "claim_version" not in (data or {}):
        view = (
            flow["client"]
            .get(f"/api/payments/bookings/{flow['booking']['id']}", headers=flow["headers"][role])
            .json()
        )
        data = {
            **(data or {}),
            "claim_version": (view.get("dispute") or {}).get("claim_version", 1),
        }
    return flow["client"].post(
        "/api/" + path,
        json={"booking_id": flow["booking"]["id"], **(data or {})},
        headers=flow["headers"][role],
    )


def fund(flow):
    first = call(flow, "payments/create-order")
    assert first.status_code == 200, first.text
    assert first.json()["amount_paise"] == 90000
    assert call(flow, "payments/create-order").json()["order_id"] == first.json()["order_id"]
    paid = call(flow, "payments/mock-confirm")
    assert paid.status_code == 200 and paid.json()["payment_status"] == "captured", paid.text


def evidence(flow, stage, role):
    import io

    from PIL import Image

    stream = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(stream, format="PNG")
    result = flow["client"].post(
        f"/api/payments/bookings/{flow['booking']['id']}/evidence?stage={stage}",
        files={"file": ("synthetic.png", stream.getvalue(), "image/png")},
        headers=flow["headers"][role],
    )
    assert result.status_code == 200, result.text
    return result.json()["url"]


def physical_return(flow):
    client, headers, rid = flow["client"], flow["headers"], flow["request_id"]
    for path, role, data in (
        ("handover/upload-photos", "lender", "handover"),
        ("handover/borrower-confirm", "borrower", {}),
        ("handover/lender-confirm", "lender", None),
        ("return/upload-photos", "borrower", "return"),
    ):
        if isinstance(data, str):
            data = {"photo_urls": [evidence(flow, data, role)]}
        result = client.post(f"/api/borrow-requests/{rid}/{path}", json=data, headers=headers[role])
        assert result.status_code == 200, result.text


def assert_balanced(flow):
    with flow["factory"]() as db:
        for row in db.scalars(select(JournalTransaction)).all():
            lines = db.scalars(
                select(EscrowLedgerEntry).where(EscrowLedgerEntry.journal_id == row.id)
            ).all()
            assert row.status == "posted"
            assert (
                sum(line.amount_paise for line in lines if line.entry_type == "DEBIT")
                == row.debit_paise
            )
            assert (
                sum(line.amount_paise for line in lines if line.entry_type == "CREDIT")
                == row.credit_paise
            )


def test_complete_mock_clean_return_refund(flow):
    locked = flow["client"].post(
        f"/api/borrow-requests/{flow['request_id']}/handover/upload-photos",
        json={"photo_urls": ["/uploads/test.png"]},
        headers=flow["headers"]["lender"],
    )
    assert locked.status_code == 409
    fund(flow)
    physical_return(flow)
    approved = flow["client"].post(
        f"/api/borrow-requests/{flow['request_id']}/return/confirm",
        json={"approved": True},
        headers=flow["headers"]["lender"],
    )
    assert approved.status_code == 200, approved.text
    state = (
        flow["client"]
        .get(f"/api/payments/bookings/{flow['booking']['id']}", headers=flow["headers"]["borrower"])
        .json()
    )
    assert state["booking_status"] == "settling" and state["deposit_refunded_paise"] == 0
    assert state["held_deposit_paise"] == 50000 and state["deduction_paise"] == 0
    assert call(flow, "payments/refund-deposit", role="lender").status_code == 200
    settled = call(flow, "payments/refunds/execute")
    assert settled.status_code == 200 and settled.json()["deposit_refunded_paise"] == 50000
    assert_balanced(flow)


def test_human_partial_settlement_and_ai_cannot_authorize(flow):
    fund(flow)
    physical_return(flow)
    claim = call(
        flow,
        "disputes/raise",
        {"claimed_deduction_paise": 20000, "reason": "Human claim: casing concern"},
        "lender",
    )
    assert claim.status_code == 200, claim.text
    assert (
        call(flow, "disputes/settle", {"approved_deduction_paise": 20000}, "lender").status_code
        == 403
    )
    assert (
        call(
            flow,
            "disputes/settle",
            {"approved_deduction_paise": 20000, "ai_approved": True},
            "lender",
        ).status_code
        == 422
    )
    assert (
        call(
            flow, "disputes/respond", {"accepted": True, "notes": "Agree to exact amount"}
        ).status_code
        == 200
    )
    assert (
        call(flow, "disputes/settle", {"approved_deduction_paise": 20000}, "lender").status_code
        == 403
    )
    assert (
        call(
            flow,
            "disputes/settle",
            {"approved_deduction_paise": 20000, "reason": "Independent evidence review"},
            "admin",
        ).status_code
        == 200
    )
    pending = call(flow, "payments/refunds/reconcile", {"demo_outcome": "pending"})
    assert pending.status_code == 200 and pending.json()["held_deposit_paise"] == 50000
    confirmed = call(flow, "payments/refunds/reconcile")
    assert confirmed.status_code == 200, confirmed.text
    state = confirmed.json()
    assert state["deposit_refunded_paise"] == 30000 and state["deduction_paise"] == 20000
    assert state["booking_status"] == "completed" and state["held_deposit_paise"] == 0
    assert_balanced(flow)


@pytest.mark.parametrize(
    "path,role,data,expected",
    [
        ("payments/create-order", "lender", {}, 403),
        ("payments/create-order", "other", {}, 403),
        ("payments/create-order", "borrower", {"amount_paise": 1}, 422),
        ("payments/refund-deposit", "lender", {}, 409),
        ("disputes/raise", "borrower", {"claimed_deduction_paise": 1, "reason": "not lender"}, 403),
        ("payments/mock-confirm", "other", {}, 403),
    ],
)
def test_authorization_and_unrestricted_financial_actions_rejected(
    flow, path, role, data, expected
):
    assert call(flow, path, data, role).status_code == expected


def test_failed_and_delayed_demo_attempts_and_duplicate_capture(flow):
    assert call(flow, "payments/create-order").status_code == 200
    assert (
        call(flow, "payments/mock-confirm", {"outcome": "failed"}).json()["payment_status"]
        == "failed"
    )
    pending = call(flow, "payments/mock-confirm", {"outcome": "pending"}).json()
    assert pending["payment_status"] == "authorized" and not pending["handover_unlocked"]
    assert call(flow, "payments/mock-confirm").json()["payment_status"] == "authorized"
    result = call(
        flow,
        "payments/mock-confirm",
        {"payment_id": pending["pending_payment_id"], "outcome": "success"},
    )
    assert result.json()["handover_unlocked"]
    assert call(flow, "payments/mock-confirm").json()["payment_status"] == "captured"
    with flow["factory"]() as db:
        assert len(db.scalars(select(JournalTransaction)).all()) == 1


@pytest.mark.parametrize("funded", [False, True])
def test_pre_receipt_cancellation(flow, funded):
    if funded:
        fund(flow)
    assert call(flow, "payments/cancel").status_code == 200
    if funded:
        state = call(flow, "payments/refunds/reconcile").json()
        assert state["refund"]["amount_paise"] == 90000 and state["booking_status"] == "cancelled"
    else:
        assert call(flow, "payments/create-order").status_code == 409
    assert_balanced(flow)


def test_failed_refund_retries_and_concurrent_settlement(flow):
    fund(flow)
    physical_return(flow)
    call(
        flow,
        "disputes/raise",
        {"claimed_deduction_paise": 20000, "reason": "Human request"},
        "lender",
    )
    call(flow, "disputes/respond", {"accepted": True, "notes": "agree"})

    def resolve(_):
        with flow["factory"]() as db:
            return PaymentService(db, flow["provider"]).resolve(
                flow["booking"]["id"],
                flow["ids"]["admin"],
                20000,
                admin=True,
                reason="Independent review of return evidence",
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(resolve, range(2)))
    assert results[0]["id"] == results[1]["id"]
    failed = call(flow, "payments/refunds/reconcile", {"demo_outcome": "failed"}).json()
    assert failed["refund"]["status"] == "failed" and failed["held_deposit_paise"] == 50000
    assert call(flow, "payments/refunds/reconcile").json()["booking_status"] == "completed"
    assert_balanced(flow)


def test_journal_database_guards_and_immutable_snapshots(flow):
    fund(flow)
    with flow["factory"]() as db:
        booking = db.get(RentalBooking, flow["booking"]["id"])
        booking.security_deposit_paise = 1
        with pytest.raises(ValueError, match="immutable"):
            db.commit()
        db.rollback()
        for command in (
            "UPDATE escrow_ledger_entries SET amount_paise=1",
            "DELETE FROM journal_transactions",
        ):
            with pytest.raises(Exception, match="append-only"):
                db.execute(text(command))
            db.rollback()


@pytest.mark.parametrize("deduction", [0, 50000, 50001])
def test_deduction_bounds_and_zero_refund(flow, deduction):
    fund(flow)
    physical_return(flow)
    claim = call(
        flow,
        "disputes/raise",
        {"claimed_deduction_paise": deduction, "reason": "Explicit human claim"},
        "lender",
    )
    if deduction > 50000:
        assert claim.status_code == 409
        return
    assert claim.status_code == 200
    call(flow, "disputes/respond", {"accepted": True, "notes": "agree"})
    assert (
        call(
            flow,
            "disputes/settle",
            {"approved_deduction_paise": deduction, "reason": "Independent evidence review"},
            "admin",
        ).status_code
        == 200
    )
    result = call(flow, "payments/refunds/reconcile").json()
    assert result["deposit_refunded_paise"] == 50000 - deduction
    assert result["deduction_paise"] == deduction and result["held_deposit_paise"] == 0
    assert_balanced(flow)


def razorpay_flow(flow):
    """Only the provider transport is replaced; real signature and service checks execute."""
    state = {
        "payment_status": "captured",
        "amount": 90000,
        "currency": "INR",
        "order_id": "order_fixture",
    }
    settings = Settings(
        _env_file=None,
        app_env="test",
        payment_provider="razorpay_test",
        payment_demo_mode=False,
        razorpay_key_id="rzp_test_fixture",
        razorpay_key_secret="fixture-secret",
        razorpay_webhook_secret="fixture-webhook",
    )

    def transport(method, path, data, headers):
        assert headers["Authorization"].startswith("Basic ")
        if path == "orders" and method == "POST":
            state["receipt"] = data["receipt"]
            if state.get("timeout"):
                raise ProviderError("provider_outcome_unknown")
            return {
                "id": "order_fixture",
                "receipt": data["receipt"],
                "amount": 90000,
                "currency": "INR",
            }
        if path.startswith("orders?"):
            return {
                "items": [
                    {
                        "id": "order_fixture",
                        "receipt": state["receipt"],
                        "amount": 90000,
                        "currency": "INR",
                    }
                ]
            }
        if path == "orders/order_fixture":
            return {
                "id": "order_fixture",
                "receipt": state["receipt"],
                "amount": 90000,
                "currency": "INR",
            }
        if path == "payments/pay_fixture":
            return {
                "id": "pay_fixture",
                "order_id": state["order_id"],
                "amount": state["amount"],
                "currency": state["currency"],
                "status": state["payment_status"],
            }
        raise AssertionError(path)

    provider = RazorpayTestProvider(settings, transport=transport)
    app.dependency_overrides[payment_provider] = lambda: provider
    signature = hmac.new(
        b"fixture-secret", b"order_fixture|pay_fixture", hashlib.sha256
    ).hexdigest()
    return state, signature


@pytest.mark.parametrize(
    "case", ["valid", "signature", "wrong_order", "wrong_amount", "wrong_currency", "uncaptured"]
)
@pytest.mark.parametrize("flow", ["razorpay_test"], indirect=True)
def test_razorpay_authoritative_verification_and_duplicate_callback(flow, case):
    state, signature = razorpay_flow(flow)
    assert call(flow, "payments/create-order").status_code == 200
    data = {"order_id": "order_fixture", "payment_id": "pay_fixture", "signature": signature}
    if case == "signature":
        data["signature"] = "0" * 64
    if case == "wrong_order":
        state["order_id"] = "order_wrong"
    if case == "wrong_amount":
        state["amount"] = 1
    if case == "wrong_currency":
        state["currency"] = "USD"
    if case == "uncaptured":
        state["payment_status"] = "authorized"
    result = call(flow, "payments/verify", data)
    if case == "signature":
        assert result.status_code == 400
    elif case.startswith("wrong"):
        assert result.status_code == 409
    else:
        assert result.status_code == 200, result.text
        assert result.json()["handover_unlocked"] is (case == "valid")
        assert call(flow, "payments/verify", data).status_code == 200
    assert_balanced(flow)


@pytest.mark.parametrize("flow", ["razorpay_test"], indirect=True)
def test_webhook_signature_durable_deduplication_and_out_of_order_events(flow):
    state, signature = razorpay_flow(flow)
    call(flow, "payments/create-order")

    def event(name, event_id, forged=False):
        raw = json.dumps(
            {
                "event": name,
                "payload": {
                    "payment": {"entity": {"id": "pay_fixture", "order_id": "order_fixture"}}
                },
            }
        ).encode()
        digest = hmac.new(b"fixture-webhook", raw, hashlib.sha256).hexdigest()
        return flow["client"].post(
            "/api/payments/webhook",
            content=raw,
            headers={
                "x-razorpay-signature": "0" * 64 if forged else digest,
                "x-razorpay-event-id": event_id,
            },
        )

    assert event("payment.captured", "forged", True).status_code == 400
    assert event("payment.captured", "capture1").status_code == 200
    assert event("payment.captured", "capture1").json()["duplicate"]
    state["payment_status"] = "authorized"
    assert event("payment.authorized", "older1").status_code == 200
    state["payment_status"] = "failed"
    assert event("payment.failed", "older2").status_code == 200
    with flow["factory"]() as db:
        assert db.get(RentalBooking, flow["booking"]["id"]).payment_status == "captured"
        assert len(db.scalars(select(JournalTransaction)).all()) == 1
    assert_balanced(flow)


@pytest.mark.parametrize("flow", ["razorpay_test"], indirect=True)
def test_uncertain_order_creation_reconciles_without_another_post(flow):
    state, signature = razorpay_flow(flow)
    state["timeout"] = True
    assert call(flow, "payments/create-order").status_code == 503
    # Existing persisted receipt locates the accepted order; create is not repeated.
    assert call(flow, "payments/create-order").status_code == 200


def test_legacy_rentals_are_not_implicitly_funded(flow):
    # A synthetic legacy request can be inspected, but every forward handover guard must fail.
    with flow["factory"]() as db:
        from app.models import BorrowRequest

        existing = db.get(BorrowRequest, flow["request_id"])
        legacy = BorrowRequest(
            borrower_id=existing.borrower_id,
            listing_id=existing.listing_id,
            title="Historical unpaid rental",
            category="Tools",
            handover_status="pending",
        )
        db.add(legacy)
        db.commit()
        rid = legacy.id
    response = flow["client"].get(
        f"/api/payments/by-request/{rid}", headers=flow["headers"]["borrower"]
    )
    assert response.json()["legacy"] and not response.json()["handover_unlocked"]
    assert (
        flow["client"]
        .post(
            f"/api/borrow-requests/{rid}/handover/upload-photos",
            json={"photo_urls": ["/uploads/test.png"]},
            headers=flow["headers"]["lender"],
        )
        .status_code
        == 409
    )


def test_rejected_return_freezes_deposit_until_explicit_claim(flow):
    fund(flow)
    physical_return(flow)
    result = flow["client"].post(
        f"/api/borrow-requests/{flow['request_id']}/return/confirm",
        json={"approved": False, "condition_note": "Human review required"},
        headers=flow["headers"]["lender"],
    )
    assert result.status_code == 200, result.text
    assert call(flow, "disputes/respond", {"accepted": True}).status_code == 409
    assert call(flow, "payments/refund-deposit", role="lender").status_code == 409
    revised = call(
        flow,
        "disputes/raise",
        {"claimed_deduction_paise": 10000, "reason": "Explicit claim amount"},
        "lender",
    )
    assert revised.status_code == 200 and revised.json()["status"] == "raised"
    assert_balanced(flow)


def test_admin_can_authorize_bounded_resolution_without_ai(flow):
    fund(flow)
    physical_return(flow)
    call(
        flow,
        "disputes/raise",
        {"claimed_deduction_paise": 30000, "reason": "Human claim"},
        "lender",
    )
    result = call(
        flow,
        "disputes/settle",
        {
            "approved_deduction_paise": 15000,
            "reason": "Reviewed the evidence and proportional damage",
        },
        "admin",
    )
    assert result.status_code == 200, result.text
    final = call(flow, "payments/refunds/reconcile", role="admin")
    assert final.status_code == 200 and final.json()["deduction_paise"] == 15000
    assert_balanced(flow)


def test_refund_unknown_outcome_retries_same_intent_without_double_posting(flow, monkeypatch):
    fund(flow)
    physical_return(flow)
    call(
        flow,
        "disputes/raise",
        {"claimed_deduction_paise": 20000, "reason": "Human claim"},
        "lender",
    )
    call(flow, "disputes/respond", {"accepted": True})
    assert (
        call(
            flow,
            "disputes/settle",
            {"approved_deduction_paise": 20000, "reason": "Independent evidence review"},
            "admin",
        ).status_code
        == 200
    )
    references = []
    original = flow["provider"].refund

    def uncertain(payment_id, amount, reference):
        references.append(reference)
        if len(references) == 1:
            raise ProviderError("provider_outcome_unknown")
        return original(payment_id, amount, reference)

    monkeypatch.setattr(flow["provider"], "refund", uncertain)
    assert call(flow, "payments/refunds/reconcile").status_code == 503
    assert call(flow, "payments/refunds/reconcile").json()["booking_status"] == "completed"
    assert call(flow, "payments/refunds/reconcile").json()["booking_status"] == "completed"
    assert len(references) == 2 and references[0] == references[1]
    assert_balanced(flow)


@pytest.mark.parametrize("flow", ["razorpay_test"], indirect=True)
@pytest.mark.parametrize("failure", ["unknown", "known_failed"])
def test_gateway_refund_recovery_preserves_history_and_requires_admin_for_new_attempt(
    flow, failure
):
    state, signature = razorpay_flow(flow)
    call(flow, "payments/create-order")
    assert (
        call(
            flow,
            "payments/verify",
            {"order_id": "order_fixture", "payment_id": "pay_fixture", "signature": signature},
        ).status_code
        == 200
    )
    physical_return(flow)
    call(
        flow,
        "disputes/raise",
        {"claimed_deduction_paise": 20000, "reason": "Human claim"},
        "lender",
    )
    call(flow, "disputes/respond", {"accepted": True})
    assert (
        call(
            flow,
            "disputes/settle",
            {"approved_deduction_paise": 20000, "reason": "Independent evidence review"},
            "admin",
        ).status_code
        == 200
    )
    provider = app.dependency_overrides[payment_provider]()
    original, refunds, requests = provider.transport, {}, []

    def transport(method, path, data, headers):
        if path == "payments/pay_fixture/refund":
            reference = headers["X-Refund-Idempotency"]
            requests.append(reference)
            if reference not in refunds:
                refunds[reference] = {
                    "id": "rfnd_fixture" + str(len(refunds)),
                    "payment_id": "pay_fixture",
                    "amount": 30000,
                    "currency": "INR",
                    "receipt": reference,
                    "status": "failed"
                    if failure == "known_failed" and not refunds
                    else "processed",
                }
                if failure == "unknown" and len(requests) == 1:
                    raise ProviderError("provider_outcome_unknown")
            return refunds[reference]
        if path.startswith("refunds/"):
            return next(row for row in refunds.values() if row["id"] == path.split("/")[1])
        if path.startswith("payments/pay_fixture/refunds?"):
            return {"items": list(refunds.values())}
        return original(method, path, data, headers)

    provider.transport = transport
    first = call(flow, "payments/refunds/execute", {"gateway_refund_approved": True})
    if failure == "unknown":
        assert first.status_code == 503
        final = call(flow, "payments/refunds/reconcile")
        assert len(set(requests)) == 1
    else:
        assert first.status_code == 200 and first.json()["refund"]["status"] == "failed"
        assert call(flow, "payments/refunds/reconcile", {"retry_failed": True}).status_code == 403
        final = call(
            flow,
            "payments/refunds/execute",
            {"retry_failed": True, "gateway_refund_approved": True},
            "admin",
        )
        assert len(set(requests)) == 2
    assert final.status_code == 200, final.text
    assert (
        final.json()["deposit_refunded_paise"] == 30000 and final.json()["deduction_paise"] == 20000
    )
    assert_balanced(flow)


def test_retired_handover_aliases_cannot_bypass_payment_or_photo_flow(flow):
    for suffix in ("mark-given", "confirm"):
        result = flow["client"].post(
            f"/api/borrow-requests/{flow['request_id']}/handover/{suffix}",
            headers=flow["headers"]["lender"],
        )
        assert result.status_code == 409
    fund(flow)
    for suffix in ("mark-given", "confirm"):
        assert (
            flow["client"]
            .post(
                f"/api/borrow-requests/{flow['request_id']}/handover/{suffix}",
                headers=flow["headers"]["lender"],
            )
            .status_code
            == 410
        )
