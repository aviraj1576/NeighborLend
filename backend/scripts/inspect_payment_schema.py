"""Read-only configured PostgreSQL catalog audit; never print connection credentials."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / ".test-tools"), str(ROOT)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--after",
        action="store_true",
        help="Save post-migration inspection without replacing the original catalog",
    )
    args = parser.parse_args()
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    from app.config import Settings

    url = make_url(Settings().database_url)
    if url.get_backend_name() != "postgresql":
        raise SystemExit("Configured database is not PostgreSQL; no inspection performed")
    engine = create_engine(url, connect_args={"connect_timeout": 12}, hide_parameters=True)
    queries = {
        "backend_role": "SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user",
        "columns": """SELECT table_name,column_name,data_type,udt_name,is_nullable,column_default
            FROM information_schema.columns WHERE table_schema='public'
            ORDER BY table_name,ordinal_position""",
        "constraints": """SELECT c.relname AS table_name,con.conname,con.contype,
            pg_get_constraintdef(con.oid) AS definition FROM pg_constraint con
            JOIN pg_class c ON c.oid=con.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' ORDER BY c.relname,con.conname""",
        "indexes": "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY tablename,indexname",
        "enums": """SELECT t.typname,e.enumlabel FROM pg_type t JOIN pg_enum e ON e.enumtypid=t.oid
            JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='public'
            ORDER BY t.typname,e.enumsortorder""",
        "triggers": """SELECT c.relname AS table_name,t.tgname,pg_get_triggerdef(t.oid) AS definition
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY c.relname,t.tgname""",
        "rls": """SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
            AND c.relkind='r' ORDER BY c.relname""",
        "policies": "SELECT * FROM pg_policies WHERE schemaname='public' ORDER BY tablename,policyname",
        "grants": """SELECT grantee,table_name,privilege_type FROM information_schema.role_table_grants
            WHERE table_schema='public' ORDER BY table_name,grantee,privilege_type""",
        "history_tables": """SELECT table_schema,table_name FROM information_schema.tables
            WHERE table_name IN ('alembic_version','schema_migrations','payment_schema_versions')""",
    }
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN READ ONLY")
            connection.exec_driver_sql("SET LOCAL statement_timeout='15s'")
            report = {
                name: [dict(row) for row in connection.execute(text(sql)).mappings()]
                for name, sql in queries.items()
            }
            connection.rollback()
        target = (
            ROOT
            / ".payment-verification"
            / "master-20261111"
            / ("hosted-schema-after.json" if args.after else "hosted-schema.json")
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        tables = sorted({row["table_name"] for row in report["columns"]})
        print(
            json.dumps(
                {
                    "read_only": True,
                    "tables": tables,
                    "constraints": len(report["constraints"]),
                    "triggers": len(report["triggers"]),
                    "report": str(target),
                }
            )
        )
    except Exception as exc:
        # Driver exception messages may contain usernames, hosts or connection strings.
        print(
            json.dumps(
                {"read_only": True, "inspection": "failed", "error_type": type(exc).__name__}
            )
        )
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
