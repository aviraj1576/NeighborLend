"""Preflight, back up and apply the approved additive financial SQL.

Defaults to read-only preflight. --apply requires an explicit reviewed SHA-256.
Uses the configured PostgreSQL connection without putting credentials in argv/logs.
Never invokes a payment provider, imports the app server, or recreates shared rows.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / ".test-tools"), str(ROOT)]
SQL_FILE = ROOT / "migrations/payments/003_supabase_financial_guards.sql"
OUTPUT = ROOT / ".payment-verification/master-20261111"


def fingerprints(connection, tables):
    result = {}
    for table in tables:
        # Only server-side hashes/counts leave the DB; no personal row data is logged.
        result[table] = dict(
            connection.exec_driver_sql(f"""SELECT count(*) AS count,
            md5(COALESCE(string_agg(md5(row_to_json(t)::text),'' ORDER BY md5(row_to_json(t)::text)),'')) AS digest
            FROM public.{table} t""")
            .mappings()
            .one()
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--sha256", help="SHA-256 of the exact reviewed SQL")
    args = parser.parse_args()
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.engine import make_url

    from app.config import Settings
    from app.services.payment_migrations import TABLES

    settings = Settings()
    url = make_url(settings.database_url)
    if url.get_backend_name() != "postgresql":
        raise SystemExit("Only the configured PostgreSQL database is supported")
    if settings.app_env.lower() in {"production", "prod"} or settings.auto_migrate:
        raise SystemExit("Production/automatic migration configuration is not permitted")
    if settings.payment_provider not in {"disabled", "razorpay_test"}:
        raise SystemExit("Only disabled or Razorpay Test configuration is permitted")
    sql_bytes = SQL_FILE.read_bytes()
    digest = hashlib.sha256(sql_bytes).hexdigest()
    if args.apply and args.sha256 != digest:
        raise SystemExit("An exact reviewed migration SHA-256 is required")
    original = json.loads((OUTPUT / "hosted-schema.json").read_text("utf-8"))
    tables = sorted({row["table_name"] for row in original["columns"]})
    if not tables or any(not name.replace("_", "").isalnum() for name in tables):
        raise SystemExit("Invalid original catalog inventory")
    engine = create_engine(url, connect_args={"connect_timeout": 15}, hide_parameters=True)
    report = {"applied": False, "migration_sha256": digest, "original_tables": tables}
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN READ ONLY")
            connection.exec_driver_sql("SET LOCAL statement_timeout='30s'")
            current = inspect(connection)
            if set(current.get_table_names(schema="public")) != set(tables):
                raise RuntimeError("Schema changed since inspection; review before applying")
            for table in tables:
                expected = {
                    row["column_name"] for row in original["columns"] if row["table_name"] == table
                }
                if {row["name"] for row in current.get_columns(table, schema="public")} != expected:
                    raise RuntimeError("Schema columns changed since inspection")
            report["before"] = fingerprints(connection, tables)
            role = connection.exec_driver_sql(
                "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user"
            ).scalar()
            if not role:
                raise RuntimeError("Backend role must be reviewed for financial RLS access")
            report["backend_role_can_access_rls"] = True
            report["server_version"] = connection.exec_driver_sql("SHOW server_version").scalar()
            connection.rollback()
        if not args.apply:
            print(
                json.dumps(
                    {
                        "preflight": "passed",
                        "read_only": True,
                        "migration_sha256": digest,
                        "original_table_count": len(tables),
                        "backend_role_can_access_rls": True,
                    }
                )
            )
            return 0
        run = OUTPUT / ("hosted-apply-" + uuid4().hex)
        run.mkdir(parents=True)
        backup = run / "public-before.dump"
        tools = ROOT / ".payment-verification/postgres-tools/extracted/pgsql/bin"
        env = os.environ.copy()
        env.update(
            PGHOST=url.host or "",
            PGPORT=str(url.port or 5432),
            PGUSER=url.username or "",
            PGPASSWORD=url.password or "",
            PGDATABASE=url.database or "",
            PGSSLMODE="require",
        )
        with (run / "backup.log").open("wb") as log:
            result = subprocess.run(
                [
                    str(tools / "pg_dump.exe"),
                    "--schema=public",
                    "--format=custom",
                    "--file=" + str(backup),
                    "--no-password",
                ],
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        if result.returncode or not backup.is_file() or not backup.stat().st_size:
            raise RuntimeError("Backup failed; no migration was attempted")
        # Verify the archive is readable before any schema mutation.
        verified = subprocess.run(
            [str(tools / "pg_restore.exe"), "--list", str(backup)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if verified.returncode:
            raise RuntimeError("Backup validation failed; no migration was attempted")
        report["backup"] = str(backup)
        report["backup_sha256"] = hashlib.sha256(backup.read_bytes()).hexdigest()
        report["backup_verified"] = True
        raw = engine.raw_connection()
        try:
            with raw.cursor() as cursor:
                # The reviewed script is atomic, with bounded statement/lock waits.
                cursor.execute(sql_bytes.decode("utf-8"))
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()
        report["applied"] = True
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN READ ONLY")
            report["after"] = fingerprints(connection, tables)
            report["original_row_counts_preserved"] = all(
                report["before"][name]["count"] == report["after"][name]["count"] for name in tables
            )
            # Nullable columns intentionally change row_to_json hashes for two
            # tables. Compare the ORIGINAL column projection for exact preservation.
            for table in tables:
                columns = [
                    row["column_name"] for row in original["columns"] if row["table_name"] == table
                ]
                projection = ",".join('"' + column.replace('"', '""') + '"' for column in columns)
                value = connection.exec_driver_sql(f"""SELECT md5(COALESCE(string_agg(md5(row_to_json(t)::text),'' ORDER BY md5(row_to_json(t)::text)),''))
                    FROM (SELECT {projection} FROM public.{table}) t""").scalar()
                if value != report["before"][table]["digest"]:
                    raise RuntimeError(
                        "Original rows changed during migration; investigate concurrent application writes"
                    )
            report["original_rows_preserved"] = True
            report["payment_schema_version"] = connection.exec_driver_sql(
                "SELECT max(version) FROM payment_schema_versions"
            ).scalar()
            inventory = []
            for table in (*TABLES, "payment_schema_versions"):
                inventory.append(
                    {
                        "table": table,
                        "rows": connection.exec_driver_sql(
                            f"SELECT count(*) FROM public.{table}"
                        ).scalar(),
                        "rls_enabled": connection.exec_driver_sql(
                            "SELECT relrowsecurity FROM pg_class WHERE oid=%s::regclass",
                            ("public." + table,),
                        ).scalar(),
                    }
                )
                for role in ("anon", "authenticated"):
                    if connection.exec_driver_sql(
                        "SELECT has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE')",
                        (role, "public." + table),
                    ).scalar():
                        raise RuntimeError("Unexpected browser financial access")
            report["tables"] = inventory
            report["browser_financial_access_denied"] = True
            connection.rollback()
        report["dashboard"] = settings.supabase_url.replace("https://", "").split(".")[0]
        (run / "verification.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    key: value
                    for key, value in report.items()
                    if key not in {"before", "after", "backup_sha256"}
                },
                default=str,
            )
        )
        return 0
    except Exception as exc:
        # Never emit driver connection strings or credentials.
        report["error_type"] = type(exc).__name__
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / "hosted-apply-error.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "applied": report["applied"],
                    "error_type": type(exc).__name__,
                    "detail": str(exc)
                    if isinstance(exc, RuntimeError)
                    else "Database operation failed; private diagnostic retained",
                }
            )
        )
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
