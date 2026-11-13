"""Provisioning/cleanup tests use synthetic fixtures and a new local DB only."""

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, insert, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import User
from scripts.provision_fictional_accounts import (
    ACCOUNTS,
    LABEL,
    ProvisioningError,
    build_cleanup_plan,
    execute_cleanup,
    match_existing,
    parse_credentials,
    validate_target,
)


@pytest.fixture
def database():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    records = [dict(id=str(uuid4()), name=name + LABEL, username=username,
                    email=username + "@example.com", is_admin=role == "Admin")
               for name, username, role in ACCOUNTS]
    outsider = dict(id=str(uuid4()), name="Unrelated", username="unrelated",
                    email="unrelated@example.com", is_admin=False)
    with engine.begin() as connection:
        for row in records + [outsider]:
            connection.execute(insert(User.__table__).values(**row, password_hash="synthetic", is_verified=True))
        yield connection, records, outsider
    engine.dispose()


def add(connection, table, **values):
    values.setdefault("id", str(uuid4()))
    connection.execute(insert(Base.metadata.tables[table]).values(**values))
    return values["id"]


def add_listing(connection, owner):
    return add(connection, "listings", owner_id=owner, name="TEST fixture", category="Tools", price_per_day=100)


def test_cleanup_removes_only_owned_users_and_nonfinancial_descendants(database):
    connection, records, outsider = database
    borrower, lender, _ = [r["id"] for r in records]
    listing = add_listing(connection, lender)
    request = add(connection, "borrow_requests", borrower_id=borrower, listing_id=listing,
                  title="TEST rental", category="Tools")
    conversation = add(connection, "conversations", borrower_id=borrower, lender_id=lender)
    add(connection, "messages", conversation_id=conversation, sender_id=borrower, content="TEST")
    add(connection, "listing_photos", listing_id=listing, url="/uploads/test-only.jpg")
    add(connection, "notifications", user_id=borrower, borrow_request_id=request,
        notification_type="test", title="TEST", message="TEST", link_url="/")
    parent = add(connection, "negotiation_offers", conversation_id=conversation, sender_id=lender,
                 listing_id=listing, borrow_request_id=request, daily_price=100, total_cost=100,
                 start_date=datetime(2026, 11, 12), end_date=datetime(2026, 11, 13))
    add(connection, "negotiation_offers", conversation_id=conversation, sender_id=borrower,
        listing_id=listing, parent_offer_id=parent, daily_price=100, total_cost=100,
        start_date=datetime(2026, 11, 12), end_date=datetime(2026, 11, 13))
    unrelated_listing = add_listing(connection, outsider["id"])
    plan = build_cleanup_plan(connection, Base.metadata, records)
    assert len(plan["users"]) == 3 and len(plan["negotiation_offers"]) == 2
    execute_cleanup(connection, Base.metadata, plan)
    assert connection.execute(select(User.__table__.c.id)).scalars().all() == [outsider["id"]]
    assert connection.execute(select(Base.metadata.tables["listings"].c.id)).scalars().all() == [unrelated_listing]
    assert "payment_transactions" not in plan


def test_cleanup_idempotent_after_owned_accounts_are_removed(database):
    connection, records, _ = database
    execute_cleanup(connection, Base.metadata, build_cleanup_plan(connection, Base.metadata, records))
    assert build_cleanup_plan(connection, Base.metadata, records) == {}


@pytest.mark.parametrize("changed_field", ["name", "username", "email", "is_admin"])
def test_cleanup_rejects_changed_identity(database, changed_field):
    connection, records, _ = database
    altered = [dict(row) for row in records]
    altered[0][changed_field] = not altered[0][changed_field] if changed_field == "is_admin" else "changed"
    with pytest.raises(ProvisioningError):
        build_cleanup_plan(connection, Base.metadata, altered)
    assert len(connection.execute(select(User.__table__.c.id)).all()) == 4


def test_cleanup_does_not_expand_to_real_conversation_participants(database):
    connection, records, outsider = database
    add(connection, "conversations", borrower_id=records[0]["id"], lender_id=outsider["id"])
    with pytest.raises(ProvisioningError, match="unrelated_data"):
        build_cleanup_plan(connection, Base.metadata, records)


def test_cleanup_preserves_real_user_notification_about_test_request(database):
    connection, records, outsider = database
    request = add(connection, "borrow_requests", borrower_id=records[0]["id"], title="TEST", category="Tools")
    add(connection, "notifications", user_id=outsider["id"], borrow_request_id=request,
        notification_type="test", title="TEST", message="TEST", link_url="/")
    with pytest.raises(ProvisioningError, match="unrelated_data"):
        build_cleanup_plan(connection, Base.metadata, records)


def test_cleanup_preserves_request_for_unrelated_listing(database):
    connection, records, outsider = database
    listing = add_listing(connection, outsider["id"])
    add(connection, "borrow_requests", borrower_id=records[0]["id"], listing_id=listing, title="TEST", category="Tools")
    with pytest.raises(ProvisioningError, match="unrelated_data"):
        build_cleanup_plan(connection, Base.metadata, records)


def test_cleanup_retains_financial_booking_and_entire_account_graph(database):
    connection, records, _ = database
    borrower, lender, _ = [r["id"] for r in records]
    listing = add_listing(connection, lender)
    request = add(connection, "borrow_requests", borrower_id=borrower, listing_id=listing, title="TEST", category="Tools")
    conversation = add(connection, "conversations", borrower_id=borrower, lender_id=lender)
    offer = add(connection, "negotiation_offers", conversation_id=conversation, sender_id=lender,
                listing_id=listing, daily_price=100, total_cost=100,
                start_date=datetime(2026, 11, 12), end_date=datetime(2026, 11, 13))
    add(connection, "rental_bookings", borrow_request_id=request, offer_id=offer, listing_id=listing,
        borrower_id=borrower, lender_id=lender, start_date=datetime(2026, 11, 12), end_date=datetime(2026, 11, 13),
        duration_days=1, daily_rate_paise=10000, rental_fee_paise=10000, security_deposit_paise=0,
        total_amount_paise=10000, provider="razorpay_test")
    with pytest.raises(ProvisioningError, match="financial_or_unknown_history_retained"):
        build_cleanup_plan(connection, Base.metadata, records)
    assert len(connection.execute(select(User.__table__.c.id)).all()) == 4


def test_cleanup_checks_application_user_references_without_fk(database):
    connection, records, outsider = database
    add(connection, "borrow_requests", borrower_id=outsider["id"], title="Real request", category="Tools",
        handover_confirmed_by=records[0]["id"])
    with pytest.raises(ProvisioningError, match="unrelated_data"):
        build_cleanup_plan(connection, Base.metadata, records)


def test_username_collision_is_rejected_without_changing_existing_user(database):
    connection, records, _ = database
    with Session(bind=connection) as db:
        proposed = [dict(records[0], email="different@example.com", password="synthetic-unused")]
        with pytest.raises(ProvisioningError, match="existing_account_conflict"):
            match_existing(db, proposed)
    assert connection.execute(select(User.__table__.c.email).where(
        User.__table__.c.id == records[0]["id"])).scalar_one() == records[0]["email"]


def test_parser_uses_existing_passwords_without_exposing_them():
    text = "\n\n".join(
        f"{name} ({role})\nUsername: {username}\nEmail: {username}@example.com\nPassword: {'x' * 33}{i}"
        for i, (name, username, role) in enumerate(ACCOUNTS)
    )
    records = parse_credentials(text)
    assert len(records) == 3 and records[2]["is_admin"]
    assert records[0]["password"] == "x" * 33 + "0"
    with pytest.raises(ProvisioningError) as error:
        parse_credentials(text.replace("Username: aarav_mehta", "Username: changed"))
    assert "x" * 33 not in str(error.value)


@pytest.mark.parametrize("url", ["sqlite:///test.db", "postgresql://user:synthetic@db.other.supabase.co/postgres"])
def test_wrong_database_is_rejected_before_any_connection(url):
    settings = SimpleNamespace(database_url=url)
    with pytest.raises(ProvisioningError):
        validate_target(settings)
