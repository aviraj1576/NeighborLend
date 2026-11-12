"""Explicit additive migration. Never merges threads or rewrites rental history."""

from pathlib import Path

from sqlalchemy import inspect, text

MIGRATION_SQL = (Path(__file__).resolve().parents[2] / "supabase" / "migrations" /
                 "20261112081704_listing_scoped_conversations.sql")

# Equivalent to the backfill in the reviewed PostgreSQL SQL artifact.
BACKFILL_SQL = """
UPDATE conversations
SET listing_id = (
    SELECT MIN(o.listing_id) FROM negotiation_offers o
    WHERE o.conversation_id = conversations.id
)
WHERE listing_id IS NULL AND id IN (
    SELECT o.conversation_id FROM negotiation_offers o
    JOIN conversations c ON c.id = o.conversation_id
    JOIN listings l ON l.id = o.listing_id AND l.owner_id = c.lender_id
    GROUP BY o.conversation_id
    HAVING COUNT(DISTINCT o.listing_id) = 1
       AND COUNT(*) = (SELECT COUNT(*) FROM negotiation_offers all_offers
                      WHERE all_offers.conversation_id = o.conversation_id)
)
"""


def migrate_conversations(engine):
    if engine.dialect.name == "postgresql":
        # Execute the exact reviewed artifact, not a second PostgreSQL migration.
        with engine.begin() as connection:
            connection.exec_driver_sql(MIGRATION_SQL.read_text(encoding="utf-8"))
        return
    if engine.dialect.name != "sqlite":
        raise RuntimeError("Unsupported conversation migration database")
    with engine.begin() as connection:
        connection.exec_driver_sql("BEGIN")  # SQLite must include DDL in rollback too.
        inspector = inspect(connection)
        if "conversations" not in inspector.get_table_names():
            return
        if "listing_id" not in {c["name"] for c in inspector.get_columns("conversations")}:
            connection.execute(text("ALTER TABLE conversations ADD COLUMN listing_id VARCHAR REFERENCES listings(id)"))
        connection.execute(text(BACKFILL_SQL))
        # A collision aborts the transaction for manual review; never auto-merge.
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_conversations_participants_listing "
                                "ON conversations (borrower_id, lender_id, listing_id)"))
