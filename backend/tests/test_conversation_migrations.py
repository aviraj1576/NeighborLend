"""Execute the reviewed migration against disposable old-schema fixtures."""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from test_listing_conversations import add_ladder, assert_history_unchanged, history, open_chat
from test_razorpay_escrow import flow as payment_flow

from app.database import migrate_schema
from app.models import BorrowRequest, Conversation, NegotiationOffer
from app.services.conversation_migrations import migrate_conversations

flow = payment_flow


def old_schema(flow):
    engine = flow["factory"].kw["bind"]
    if engine.dialect.name == "sqlite":
        # Rebuild only this fixture's disposable table; SQLite cannot DROP a
        # column with a table-level FK. Preserve every ID and all dependent rows.
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.exec_driver_sql("BEGIN")
            connection.exec_driver_sql("""CREATE TABLE conversations_legacy (
                id VARCHAR PRIMARY KEY, borrower_id VARCHAR NOT NULL REFERENCES users(id),
                lender_id VARCHAR NOT NULL REFERENCES users(id), created_at DATETIME, updated_at DATETIME)""")
            connection.exec_driver_sql("""INSERT INTO conversations_legacy
                SELECT id,borrower_id,lender_id,created_at,updated_at FROM conversations""")
            connection.exec_driver_sql("DROP TABLE conversations")
            connection.exec_driver_sql("ALTER TABLE conversations_legacy RENAME TO conversations")
            connection.commit()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        return engine
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX uq_conversations_participants_listing"))
        connection.execute(text("ALTER TABLE conversations DROP COLUMN listing_id"))
    return engine


@pytest.mark.parametrize("flow", ["mock", "postgres"], indirect=True)
def test_backfill_retains_camera_ids_and_full_history_and_is_repeatable(flow):
    before = history(flow)
    original_offer = next(iter(before["negotiation_offers"].values()))
    engine = old_schema(flow)
    migrate_conversations(engine)
    migrate_conversations(engine)
    migrate_schema(engine)  # The application helper must never drop listing scope again.
    with flow["factory"]() as db:
        assert db.get(Conversation, original_offer["conversation_id"]).listing_id == original_offer["listing_id"]
    camera = open_chat(flow, original_offer["listing_id"])
    assert camera["id"] == original_offer["conversation_id"]
    assert open_chat(flow, add_ladder(flow))["id"] != camera["id"]
    assert_history_unchanged(before, history(flow))
    assert any(index["name"] == "uq_conversations_participants_listing" and index["unique"]
               for index in inspect(engine).get_indexes("conversations"))
    assert any(fk["constrained_columns"] == ["listing_id"] for fk in inspect(engine).get_foreign_keys("conversations"))


@pytest.mark.parametrize("flow", ["mock", "postgres"], indirect=True)
def test_mixed_history_remains_unassigned_and_intact(flow):
    ladder_id = add_ladder(flow)
    with flow["factory"]() as db:
        camera = db.get(BorrowRequest, flow["request_id"])
        accepted = db.query(NegotiationOffer).filter_by(borrow_request_id=camera.id).one()
        mixed_id = accepted.conversation_id
        db.add(NegotiationOffer(conversation_id=mixed_id, listing_id=ladder_id,
                               sender_id=flow["ids"]["borrower"], daily_price=125,
                               start_date=accepted.start_date, end_date=accepted.end_date,
                               total_cost=250))
        db.commit()
    before = history(flow)
    migrate_conversations(old_schema(flow))
    with flow["factory"]() as db:
        assert db.get(Conversation, mixed_id).listing_id is None
    ladder = open_chat(flow, ladder_id)
    assert ladder["id"] != mixed_id and ladder["offers"] == []
    assert_history_unchanged(before, history(flow))


@pytest.mark.parametrize("flow", ["mock", "postgres"], indirect=True)
def test_duplicate_legacy_threads_abort_instead_of_merging(flow):
    with flow["factory"]() as db:
        original = db.query(NegotiationOffer).one()
        duplicate = Conversation(borrower_id=flow["ids"]["borrower"], lender_id=flow["ids"]["lender"])
        db.add(duplicate)
        db.flush()
        db.add(NegotiationOffer(conversation_id=duplicate.id, listing_id=original.listing_id,
                               sender_id=original.sender_id, daily_price=original.daily_price,
                               start_date=original.start_date, end_date=original.end_date,
                               total_cost=original.total_cost))
        db.commit()
    engine = old_schema(flow)
    before = history(flow)
    with pytest.raises(IntegrityError):
        migrate_conversations(engine)
    assert "listing_id" not in {c["name"] for c in inspect(engine).get_columns("conversations")}
    assert_history_unchanged(before, history(flow))
