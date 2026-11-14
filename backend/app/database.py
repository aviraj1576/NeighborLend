from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import get_settings

settings = get_settings()

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_schema(target_engine=None):
    """Apply additive schema changes needed by existing installations."""
    target_engine = target_engine or engine
    additions = {
        "users": {
            "is_verified": "BOOLEAN NOT NULL DEFAULT TRUE",
            "google_sub": "VARCHAR",
        },
        "borrow_requests": {
            "returned_at": "DATETIME",
            "disputed_at": "DATETIME",
            "dispute_description": "TEXT",
            "handover_status": "VARCHAR NOT NULL DEFAULT 'not_applicable'",
            "handover_marked_at": "DATETIME",
            "handover_confirmed_at": "DATETIME",
            "handover_confirmed_by": "VARCHAR",
            "handover_issue_description": "TEXT",
            "handover_issue_reported_at": "DATETIME",
            "handover_photos": "TEXT",
            "handover_confirmed_photos": "TEXT",
            "return_photos": "TEXT",
            "return_confirmed_at": "DATETIME",
            "return_confirmed_by": "VARCHAR",
            "borrowing_started_at": "DATETIME",
            "return_due_at": "DATETIME",
            "lender_rating": "INTEGER",
            "borrower_rating": "INTEGER",
            "lender_rating_comment": "TEXT",
            "borrower_rating_comment": "TEXT",
            "lender_rated_at": "DATETIME",
            "borrower_rated_at": "DATETIME",
            "damage_check_id": "VARCHAR",
            "damage_link_token": "VARCHAR",
            "damage_link_expires_at": "DATETIME",
        },
        "negotiation_offers": {
            "listing_id": "VARCHAR",
        },
    }

    with target_engine.begin() as connection:
        inspector = inspect(connection)
        existing_tables = set(inspector.get_table_names())
        for table_name, columns in additions.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            for column_name, column_definition in columns.items():
                if column_name not in existing_columns:
                    if connection.dialect.name == "postgresql":
                        column_definition = column_definition.replace("DATETIME", "TIMESTAMP")
                    connection.execute(text(
                        f"ALTER TABLE {table_name} ADD COLUMN "
                        f"{column_name} {column_definition}"
                    ))
        if "users" in existing_tables:
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_sub "
                "ON users (google_sub)"
            ))
        if "borrow_requests" in existing_tables:
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_borrow_requests_damage_link_token "
                "ON borrow_requests (damage_link_token)"
            ))

        # Move the old conversation-level listing association onto historical
        # offers before removing it. This keeps existing negotiations intact.
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if "conversations" in tables and "negotiation_offers" in tables:
            conversation_columns = {c["name"] for c in inspector.get_columns("conversations")}
            offer_columns = {c["name"] for c in inspector.get_columns("negotiation_offers")}
            if "listing_id" in conversation_columns:
                if "listing_id" not in offer_columns:
                    connection.execute(text("ALTER TABLE negotiation_offers ADD COLUMN listing_id VARCHAR"))
                connection.execute(text(
                    "UPDATE negotiation_offers SET listing_id = "
                    "(SELECT conversations.listing_id FROM conversations "
                    "WHERE conversations.id = negotiation_offers.conversation_id) "
                    "WHERE listing_id IS NULL"
                ))

                quote = connection.dialect.identifier_preparer.quote
                if connection.dialect.name == "postgresql":
                    has_listing_fk = any(
                        "listing_id" in fk.get("constrained_columns", [])
                        for fk in inspector.get_foreign_keys("negotiation_offers")
                    )
                    if not has_listing_fk:
                        connection.execute(text(
                            "ALTER TABLE negotiation_offers ADD CONSTRAINT "
                            "fk_negotiation_offers_listing_id_listings "
                            "FOREIGN KEY (listing_id) REFERENCES listings (id)"
                        ))
                    has_listing_index = any(
                        "listing_id" in (idx.get("column_names") or [])
                        for idx in inspector.get_indexes("negotiation_offers")
                    )
                    if not has_listing_index:
                        connection.execute(text(
                            "CREATE INDEX ix_negotiation_offers_listing_id "
                            "ON negotiation_offers (listing_id)"
                        ))
                if connection.dialect.name == "postgresql":
                    for foreign_key in inspector.get_foreign_keys("conversations"):
                        if "listing_id" in foreign_key.get("constrained_columns", []):
                            name = foreign_key.get("name")
                            if name:
                                connection.execute(text(
                                    f"ALTER TABLE conversations DROP CONSTRAINT {quote(name)}"
                                ))
                for index in inspector.get_indexes("conversations"):
                    if "listing_id" in (index.get("column_names") or []):
                        connection.execute(text(
                            f"DROP INDEX IF EXISTS {quote(index['name'])}"
                        ))
                connection.execute(text("ALTER TABLE conversations DROP COLUMN listing_id"))
