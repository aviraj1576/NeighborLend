"""Validate/export financial migrations against a dedicated LOCAL PostgreSQL DB.

Replays catalog definitions only, never hosted rows. The local database must be
new and empty. Uses PAYMENT_TEST_POSTGRES_URL, never the application's .env URL.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / ".test-tools"), str(ROOT)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-sql",
        action="store_true",
        help="Apply the exported SQL twice instead of the Python migrator",
    )
    args = parser.parse_args()
    from sqlalchemy import create_engine, event, inspect
    from sqlalchemy.engine import make_url

    url = make_url(os.environ["PAYMENT_TEST_POSTGRES_URL"])
    if (
        url.get_backend_name() != "postgresql"
        or url.host not in {"127.0.0.1", "localhost"}
        or not (url.database or "").startswith("neighborlend_test_")
    ):
        raise SystemExit("Only a dedicated local neighborlend_test_* database is allowed")
    # Prevent imports from binding to the configured shared DB.
    os.environ.update(
        DATABASE_URL=url.render_as_string(hide_password=False),
        PAYMENT_PROVIDER="disabled",
        AUTO_MIGRATE="false",
    )
    from app import models  # noqa: F401 - register existing application tables.
    from app.services.payment_migrations import TABLES, migrate_payments

    engine = create_engine(url, hide_parameters=True)
    if inspect(engine).get_table_names():
        raise SystemExit("Catalog replay requires an empty generated database")
    catalog = json.loads(
        (ROOT / ".payment-verification/master-20261111/hosted-schema.json").read_text("utf-8")
    )
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as connection:
        for role in ("anon", "authenticated"):
            if not connection.exec_driver_sql(
                "SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)
            ).scalar():
                connection.exec_driver_sql(f"CREATE ROLE {role} NOLOGIN")
        enums = {}
        for row in catalog["enums"]:
            enums.setdefault(row["typname"], []).append(row["enumlabel"])
        for name, labels in enums.items():
            literals = ",".join("'" + label.replace("'", "''") + "'" for label in labels)
            connection.exec_driver_sql(f"CREATE TYPE {quote(name)} AS ENUM ({literals})")
        tables = {}
        for column in catalog["columns"]:
            tables.setdefault(column["table_name"], []).append(column)
        for name, columns in tables.items():
            definitions = []
            for column in columns:
                dtype = (
                    quote(column["udt_name"])
                    if column["data_type"] == "USER-DEFINED"
                    else column["data_type"]
                )
                definition = f"{quote(column['column_name'])} {dtype}"
                if column["is_nullable"] == "NO":
                    definition += " NOT NULL"
                if column["column_default"] is not None:
                    definition += " DEFAULT " + column["column_default"]
                definitions.append(definition)
            connection.exec_driver_sql(f"CREATE TABLE {quote(name)} ({','.join(definitions)})")
        # All referenced primary/unique keys must exist before foreign keys.
        for constraint in sorted(catalog["constraints"], key=lambda row: row["contype"] == "f"):
            connection.exec_driver_sql(
                f"ALTER TABLE {quote(constraint['table_name'])} ADD CONSTRAINT {quote(constraint['conname'])} {constraint['definition']}"
            )
        for index in catalog["indexes"]:
            # Constraint indexes were created with their primary/unique constraints.
            if not connection.exec_driver_sql(
                "SELECT to_regclass(%s)", (index["indexname"],)
            ).scalar():
                connection.exec_driver_sql(index["indexdef"])
    statements = []

    def record(connection, cursor, statement, parameters, context, executemany):
        if (
            statement.lstrip()
            .upper()
            .startswith(
                (
                    "CREATE ",
                    "ALTER ",
                    "DROP TRIGGER ",
                    "REVOKE ",
                    "INSERT INTO PAYMENT_SCHEMA_VERSIONS",
                )
            )
        ):
            statements.append(statement.strip())

    if args.verify_sql:
        source = ROOT / "migrations/payments/003_supabase_financial_guards.sql"
        for _ in range(2):
            connection = engine.raw_connection()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(source.read_text("utf-8"))
                connection.commit()
            finally:
                connection.close()
    else:
        event.listen(engine, "before_cursor_execute", record)
        migrate_payments(engine)
        event.remove(engine, "before_cursor_execute", record)
        migrate_payments(engine)
    assert set(TABLES) <= set(inspect(engine).get_table_names())
    assert inspect(engine).get_columns("rental_bookings")[0]["type"] is not None
    with engine.connect() as connection:
        from sqlalchemy import select

        from app.database import Base

        for table in Base.metadata.sorted_tables:
            # Prove every current ORM column is selectable against the migrated
            # original schema, rather than assuming create_all proves compatibility.
            connection.execute(select(table).limit(0))
        assert (
            connection.exec_driver_sql("SELECT max(version) FROM payment_schema_versions").scalar()
            == 3
        )
        rls = connection.exec_driver_sql(
            """SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relrowsecurity AND c.relname=ANY(%s)""",
            (list(TABLES),),
        ).scalar()
        assert rls == len(TABLES)
        for role in ("anon", "authenticated"):
            for table in TABLES:
                assert not connection.exec_driver_sql(
                    "SELECT has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE')", (role, table)
                ).scalar()
    if args.verify_sql:
        print(
            json.dumps(
                {
                    "sql_applied_twice": True,
                    "orm_compatible": True,
                    "rls_and_browser_role_denial": True,
                    "financial_tables": len(TABLES),
                }
            )
        )
        engine.dispose()
        return
    # Reviewable SQL extends the SAME payment_schema_versions history.
    # Make creation and additive columns safe to replay, as the Python migrator is.
    sql = "-- Generated from migrate_payments against the inspected hosted catalog, locally.\n"
    sql += "-- REVIEW AND APPROVAL REQUIRED BEFORE HOSTED EXECUTION.\nBEGIN;\nSET LOCAL lock_timeout='5s';\nSET LOCAL statement_timeout='60s';\nSET LOCAL search_path=public;\n"
    for statement in statements:
        statement = re.sub(
            r"^CREATE TABLE (?!IF NOT EXISTS)", "CREATE TABLE IF NOT EXISTS ", statement
        )
        statement = re.sub(
            r"^CREATE (UNIQUE )?INDEX (?!IF NOT EXISTS)",
            lambda match: "CREATE " + (match[1] or "") + "INDEX IF NOT EXISTS ",
            statement,
        )
        statement = re.sub(
            r"(ALTER TABLE \w+ ADD COLUMN) (?!IF NOT EXISTS)", r"\1 IF NOT EXISTS ", statement
        )
        sql += statement + ";\n\n"
    sql += "COMMIT;\n"
    target = ROOT / "migrations/payments/003_supabase_financial_guards.sql"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(line.rstrip() for line in sql.splitlines()) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "catalog_replayed_without_rows": True,
                "migration_repeatable": True,
                "financial_tables": len(TABLES),
                "rls_and_browser_role_denial": True,
                "sql_statements": len(statements),
                "sql": str(target),
            }
        )
    )
    engine.dispose()


if __name__ == "__main__":
    main()
