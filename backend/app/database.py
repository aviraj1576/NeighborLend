from sqlalchemy import create_engine, inspect, text, event
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

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=15000")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_generic_schema_target_allowed(target_engine):
    """Hosted Supabase DDL must use separately reviewed SQL, never initialization."""
    if target_engine.dialect.name != "postgresql":
        return
    url = target_engine.url
    query_hosts = url.query.get("host", ())
    if isinstance(query_hosts, str):
        query_hosts = (query_hosts,)
    # libpq host overrides/multi-host URLs can replace the URL's apparent host.
    for hosts in (url.host or "", *query_hosts):
        for host in hosts.split(","):
            hostname = host.strip().lower().split(":", 1)[0].rstrip(".")
            if hostname.endswith((".supabase.co", ".supabase.com")):
                raise RuntimeError(
                    "Generic schema initialization is disabled for hosted Supabase. "
                    "Use separately reviewed and explicitly authorized migration SQL."
                )


def migrate_schema(target_engine=None):
    """Apply additive schema changes needed by existing installations."""
    target_engine = target_engine or engine
    require_generic_schema_target_allowed(target_engine)
    from app.services.payment_migrations import migrate_payments
    migrate_payments(target_engine)
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

    # Explicit migration only; AUTO_MIGRATE remains disabled by default.
    from app.services.conversation_migrations import migrate_conversations
    migrate_conversations(target_engine)
