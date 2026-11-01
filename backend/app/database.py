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


def migrate_schema():
    """Apply additive schema changes needed by existing installations."""
    additions = {
        "users": {
            "is_verified": "BOOLEAN NOT NULL DEFAULT TRUE",
            "google_sub": "VARCHAR",
        },
        "borrow_requests": {
            "returned_at": "DATETIME",
            "disputed_at": "DATETIME",
            "dispute_description": "TEXT",
        },
    }

    with engine.begin() as connection:
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
