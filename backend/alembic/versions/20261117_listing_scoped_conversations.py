"""Add listing scope to conversations without changing conversation history.

Revision ID: 20261117_listing_scope
Revises: None (standalone revision; this repository has no prior Alembic chain)
Create Date: 2026-11-17
"""

from alembic import op
import sqlalchemy as sa


revision = "20261117_listing_scope"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL DDL is transactional under Alembic's normal transaction. Keep
    # the lock bounded so a busy production service fails cleanly and rolls back.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("LOCK TABLE conversations IN ACCESS EXCLUSIVE MODE")

    # Exact Conversation model contract: String/VARCHAR, nullable, FK to listings.id.
    op.add_column(
        "conversations",
        sa.Column("listing_id", sa.String(), nullable=True),
    )
    op.create_foreign_key(
        "conversations_listing_id_fkey",
        "conversations",
        "listings",
        ["listing_id"],
        ["id"],
    )

    # Assign only threads whose every offer points to the same listing and
    # whose listing is owned by this conversation's lender. Mixed, incomplete,
    # and owner-mismatched histories remain NULL.
    op.execute(
        sa.text(
            """
            UPDATE conversations AS c
            SET listing_id = candidate.listing_id
            FROM (
                SELECT o.conversation_id, MIN(o.listing_id) AS listing_id
                FROM negotiation_offers AS o
                JOIN conversations AS source ON source.id = o.conversation_id
                JOIN listings AS l
                  ON l.id = o.listing_id
                 AND l.owner_id = source.lender_id
                GROUP BY o.conversation_id
                HAVING COUNT(DISTINCT o.listing_id) = 1
                   AND COUNT(*) = (
                       SELECT COUNT(*)
                       FROM negotiation_offers AS all_offers
                       WHERE all_offers.conversation_id = o.conversation_id
                   )
            ) AS candidate
            WHERE c.id = candidate.conversation_id
              AND c.listing_id IS NULL
            """
        )
    )

    # Validate after backfill and before index creation. Never merge or delete
    # duplicate threads; raise to roll the entire migration back for review.
    duplicate = op.get_bind().execute(
        sa.text(
            """
            SELECT borrower_id, lender_id, listing_id, COUNT(*) AS thread_count
            FROM conversations
            WHERE listing_id IS NOT NULL
            GROUP BY borrower_id, lender_id, listing_id
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate:
        raise RuntimeError(
            "Duplicate scoped conversations exist for a borrower, lender, and listing; "
            "review them before applying the unique index"
        )

    op.create_index(
        "uq_conversations_participants_listing",
        "conversations",
        ["borrower_id", "lender_id", "listing_id"],
        unique=True,
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("LOCK TABLE conversations IN ACCESS EXCLUSIVE MODE")

    # The column may now contain historical backfills or associations created
    # after upgrade. Refuse to discard those mappings during downgrade.
    has_associations = op.get_bind().execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM conversations WHERE listing_id IS NOT NULL)"
        )
    ).scalar()
    if has_associations:
        raise RuntimeError(
            "Cannot downgrade: conversations.listing_id contains associations. "
            "Preserve those mappings before removing this column."
        )

    op.drop_index(
        "uq_conversations_participants_listing", table_name="conversations"
    )
    op.drop_constraint(
        "conversations_listing_id_fkey", "conversations", type_="foreignkey"
    )
    op.drop_column("conversations", "listing_id")
