"""Explicit, local-operator provisioning of three authorized shared test accounts.

Default: read-only preflight. --apply inserts missing users only. --verify checks
the actual listener on 127.0.0.1:8000. --cleanup previews a strictly scoped cleanup;
--cleanup --apply executes it. Financial history and mixed-user records block
cleanup rather than being deleted. No schema or payment operations are provided.
"""

import argparse
import json
import logging
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / ".test-tools"), str(ROOT)]
PRIVATE = ROOT / ".payment-demo/fictional-accounts-20261112"
MANIFEST = PRIVATE / "shared-provisioning.json"
REPORT = PRIVATE / "shared-verification.json"
EXPECTED_PROJECT = "lgurfoppprubxbclpoqk"  # Previously reviewed NeighborLend project.
LABEL = " [TEST - Razorpay Test Mode]"
ACCOUNTS = (
    ("Aarav Mehta", "aarav_mehta", "Borrower"),
    ("Rohan Kapoor", "rohan_kapoor", "Lender"),
    ("Priya Sharma", "priya_sharma", "Admin"),
)
DELETE_ORDER = (
    "notifications", "email_verifications", "messages", "negotiation_offers",
    "conversations", "borrow_requests", "listing_photos", "listings", "users",
)
USER_REFERENCES_WITHOUT_FK = {
    "actor_id", "initiated_by", "borrower_id_snapshot", "lender_id_snapshot",
    "handover_confirmed_by", "return_confirmed_by",
}


class ProvisioningError(RuntimeError):
    """Only fixed, non-sensitive diagnostic codes may be used here."""


def require(condition, code):
    if not condition:
        raise ProvisioningError(code)


def parse_credentials(contents):
    records = []
    for name, username, role in ACCOUNTS:
        pattern = (
            r"(?m)^" + re.escape(f"{name} ({role})")
            + r"\r?\nUsername: ([^\r\n]+)\r?\nEmail: ([^\r\n]+)"
            + r"\r?\nPassword: ([^\r\n]+)$"
        )
        matches = re.findall(pattern, contents)
        require(len(matches) == 1, "private_credential_structure_invalid")
        actual_username, email, password = matches[0]
        require(actual_username == username and 32 <= len(password.encode()) <= 72,
                "private_credential_fields_invalid")
        records.append(dict(name=name, username=username, email=email.lower(),
                            password=password, is_admin=role == "Admin"))
    require(len({r["password"] for r in records}) == 3, "passwords_not_unique")
    return records


def inputs():
    from app.services.auth import verify_password

    credential_path = PRIVATE / "test-credentials.txt"
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", str(credential_path)], cwd=ROOT,
        capture_output=True, check=False,
    )
    require(ignored.returncode == 0, "private_credentials_must_be_git_ignored")
    records = parse_credentials(credential_path.read_text(encoding="utf-8"))
    source = PRIVATE / "verified-accounts.sqlite3"
    # The original fixtures are evidence for the explicitly authorized test-only
    # verification/admin bootstrap, not a reason to weaken public registration.
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as db:
        for record in records:
            row = db.execute(
                "SELECT name,email,password_hash,is_verified,is_admin FROM users WHERE username=?",
                (record["username"],),
            ).fetchone()
            require(row is not None and row[0] == record["name"]
                    and row[1] == record["email"] and bool(row[3])
                    and bool(row[4]) == record["is_admin"]
                    and verify_password(record["password"], row[2]),
                    "original_local_account_verification_failed")
    return records


def validate_target(settings):
    from sqlalchemy.engine import make_url

    from app.services.razorpay_service import configured_provider

    url = make_url(settings.database_url)
    require(url.get_backend_name() == "postgresql", "postgresql_required")
    direct = url.host == f"db.{EXPECTED_PROJECT}.supabase.co"
    pooled = ((url.host or "").endswith(".pooler.supabase.com")
              and (url.username or "").endswith("." + EXPECTED_PROJECT))
    require(direct or pooled, "database_project_mismatch")
    require(urlsplit(settings.supabase_url).hostname == f"{EXPECTED_PROJECT}.supabase.co",
            "supabase_project_mismatch")
    require(not settings.auto_migrate and settings.app_env.lower() not in {"prod", "production"},
            "nonproduction_without_migrations_required")
    require(settings.payment_provider == "razorpay_test"
            and configured_provider(settings).sandbox_only, "razorpay_test_mode_required")
    return url


def write_private(path, value):
    # This directory already has a protected developer-only NTFS ACL. Temporary
    # files inherit the same permissions; no credential values are stored here.
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else None


def fingerprints(connection, metadata, excluded_users=()):
    from sqlalchemy import bindparam, text

    result = {}
    for table in metadata.sorted_tables:
        name = connection.dialect.identifier_preparer.quote(table.name)
        where = " WHERE id NOT IN :excluded" if table.name == "users" and excluded_users else ""
        query = text(
            "SELECT count(*) AS count, md5(COALESCE(string_agg("
            "md5(row_to_json(t)::text), '' ORDER BY md5(row_to_json(t)::text)), '')) AS digest "
            f"FROM public.{name} t{where}"
        )
        if where:
            query = query.bindparams(bindparam("excluded", expanding=True))
        result[table.name] = dict(connection.execute(query, {"excluded": list(excluded_users)}).mappings().one())
    return result


def match_existing(db, records):
    from sqlalchemy import func, or_, select

    from app.models import User
    from app.services.auth import verify_password

    result = []
    for record in records:
        candidates = db.scalars(select(User).where(or_(
            func.lower(User.username) == record["username"], func.lower(User.email) == record["email"],
        ))).all()
        require(len(candidates) <= 1, "username_email_collision")
        existing = candidates[0] if candidates else None
        if existing is not None:
            require(existing.username == record["username"] and existing.email == record["email"]
                    and existing.name in {record["name"], record["name"] + LABEL}
                    and existing.is_verified and bool(existing.is_admin) == record["is_admin"]
                    and verify_password(record["password"], existing.password_hash),
                    "existing_account_conflict_no_modification_permitted")
        result.append(existing)
    return result


def check_authentication(db, records):
    from fastapi import HTTPException

    from app.routers.auth import login
    from app.schemas.auth import LoginIn
    from app.services.auth import get_current_user, require_admin
    from app.services.payments import authorize

    users = []
    for record in records:
        for identifier in (record["email"], record["username"]):
            result = login(LoginIn(username_or_email=identifier, password=record["password"]), db)
            user = get_current_user(result["access_token"], db)
            require(user.username == record["username"] and bool(user.is_admin) == record["is_admin"],
                    "backend_authentication_failed")
        users.append(user)
        try:
            require_admin(user)
            allowed = True
        except HTTPException as exc:
            require(exc.status_code == 403, "unexpected_admin_authorization_error")
            allowed = False
        require(allowed == record["is_admin"], "admin_authorization_failed")
    booking = SimpleNamespace(borrower_id=users[0].id, lender_id=users[1].id)
    for user, role, expected in (
        (users[0], "borrower", True), (users[1], "borrower", False),
        (users[1], "lender", True), (users[0], "lender", False),
    ):
        try:
            authorize(booking, user.id, **{role: True})
            allowed = True
        except HTTPException as exc:
            require(exc.status_code == 403, "unexpected_rental_authorization_error")
            allowed = False
        require(allowed == expected, "borrower_lender_authorization_failed")
    authorize(booking, users[2].id, admin=bool(users[2].is_admin))
    return {u.username: u.id for u in users}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def check_port_8000(records, expected_ids):
    opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(method, path, payload=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        data = json.dumps(payload).encode() if payload is not None else None
        try:
            with opener.open(Request("http://127.0.0.1:8000" + path, data=data,
                                     headers=headers, method=method), timeout=30) as response:
                return response.status, json.loads(response.read(2_000_000))
        except HTTPError as exc:
            exc.close()
            return exc.code, None

    require(request("GET", "/api/health")[0] == 200, "port_8000_health_failed")
    results = []
    for record in records:
        status, result = request("POST", "/api/auth/login", {
            "username_or_email": record["username"], "password": record["password"],
        })
        require(status == 200, "port_8000_login_failed")
        token = result["access_token"]
        status, profile = request("GET", "/api/auth/me", token=token)
        require(status == 200 and profile["id"] == expected_ids[record["username"]]
                and bool(profile["is_admin"]) == record["is_admin"],
                "port_8000_shared_identity_mismatch")
        status, listings = request("GET", "/api/listings", token=token)
        require(status == 200 and all(row["owner_id"] == profile["id"] for row in listings),
                "port_8000_listing_ownership_failed")
        status, requests = request("GET", "/api/borrow-requests/my", token=token)
        require(status == 200 and all(row["borrower_id"] == profile["id"] for row in requests),
                "port_8000_borrower_ownership_failed")
        status, _ = request("GET", "/api/disputes", token=token)
        require(status == (200 if record["is_admin"] else 403), "port_8000_admin_authorization_failed")
        results.append({"username": record["username"], "login": "passed",
                        "profile": "passed", "ownership_reads": "passed", "admin_check": "passed"})
    return results


def build_cleanup_plan(connection, metadata, owned_records):
    """Discover dependencies, refuse mixed ownership/financial history, never CASCADE."""
    from sqlalchemy import or_, select

    tables = {t.name: t for t in metadata.tables.values()}
    for table in tables.values():
        for fk in table.foreign_keys:
            require(len(fk.column.table.primary_key.columns) == 1 and fk.column.primary_key,
                    "cleanup_unsupported_foreign_key_target")
    scope = {name: set() for name in tables}
    users = tables["users"]
    require(len({r["id"] for r in owned_records}) == len(owned_records), "duplicate_manifest_ids")
    for record in owned_records:
        require(record["username"] in {a[1] for a in ACCOUNTS}
                and record["name"].endswith(LABEL), "unrecognized_manifest_account")
        row = connection.execute(select(users).where(users.c.id == record["id"])).mappings().first()
        if row is not None:
            require(all(row[field] == record[field] for field in ("username", "email", "name", "is_admin")),
                    "cleanup_account_identity_changed")
            scope["users"].add(row["id"])

    def primary_key(table):
        columns = list(table.primary_key.columns)
        require(len(columns) == 1, "cleanup_unknown_primary_key")
        return columns[0]

    # Include every FK descendant, including self-referencing offer chains. Also
    # inspect application user references that deliberately have no SQL FK.
    changed = True
    while changed:
        changed = False
        for name, table in tables.items():
            predicates = [fk.parent.in_(scope[fk.column.table.name])
                          for fk in table.foreign_keys if scope.get(fk.column.table.name)]
            predicates += [table.c[col].in_(scope["users"]) for col in USER_REFERENCES_WITHOUT_FK
                           if col in table.c and scope["users"]]
            if not predicates:
                continue
            rows = connection.execute(select(table).where(or_(*predicates))).mappings().all()
            if rows:
                require(name in DELETE_ORDER, "cleanup_financial_or_unknown_history_retained")
            for row in rows:
                key = row[primary_key(table).name]
                if key not in scope[name]:
                    scope[name].add(key)
                    changed = True

    for name in DELETE_ORDER:
        table = tables.get(name)
        if table is None or not scope[name]:
            continue
        rows = connection.execute(select(table).where(primary_key(table).in_(scope[name]))).mappings()
        for row in rows:
            for fk in table.foreign_keys:
                value = row[fk.parent.name]
                require(value is None or value in scope[fk.column.table.name],
                        "cleanup_related_record_involves_unrelated_data")
            for col in USER_REFERENCES_WITHOUT_FK:
                if col in table.c:
                    require(row[col] is None or row[col] in scope["users"],
                            "cleanup_related_record_involves_unrelated_user")
    return {name: scope[name] for name in DELETE_ORDER if scope.get(name)}


def execute_cleanup(connection, metadata, plan):
    from sqlalchemy import delete

    tables = {t.name: t for t in metadata.tables.values()}
    for name in DELETE_ORDER:
        if plan.get(name):
            table = tables[name]
            key = list(table.primary_key.columns)[0]
            connection.execute(delete(table).where(key.in_(plan[name])))


def provision(engine, metadata, records, apply):
    from sqlalchemy.orm import Session

    from app.models import User
    from app.services.auth import hash_password

    previous = read_manifest()
    require(previous is None or previous.get("project") == EXPECTED_PROJECT, "manifest_project_mismatch")
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL statement_timeout='30s'")
        connection.exec_driver_sql("SET LOCAL lock_timeout='5s'")
        connection.exec_driver_sql("LOCK TABLE public.users IN SHARE ROW EXCLUSIVE MODE")
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            existing = match_existing(db, records)
            if not apply:
                return {"preflight": "passed", "intended_project_verified": True,
                        "razorpay_test_mode": True,
                        "accounts": [{"username": r["username"], "status": "exists" if u else "missing"}
                                     for r, u in zip(records, existing, strict=True)]}
            baseline = fingerprints(connection, metadata)
            created = []
            statuses = []
            for record, user in zip(records, existing, strict=True):
                if user is None:
                    fields = {key: record[key] for key in ("username", "email", "is_admin")}
                    fields.update(id=str(uuid4()), name=record["name"] + LABEL)
                    created.append(fields)
                    user = User(**fields, password_hash=hash_password(record["password"]), is_verified=True)
                    db.add(user)
                statuses.append({"username": record["username"], "status": "created" if user in db.new else "already_present"})
            owned = {r["id"]: r for r in (previous or {}).get("created", [])}
            owned.update({r["id"]: r for r in created})
            manifest = {"project": EXPECTED_PROJECT, "state": "pending_commit", "created": list(owned.values())}
            # Persist IDs before committing so a crash cannot lose cleanup scope.
            write_private(MANIFEST, manifest)
            db.flush()
            identities = check_authentication(db, records)
            db.commit()  # Release our savepoint; the outer transaction still controls commit.
            require(baseline == fingerprints(connection, metadata, [r["id"] for r in created]),
                    "unrelated_record_fingerprint_changed_transaction_rolled_back")
    manifest["state"] = "committed"
    write_private(MANIFEST, manifest)
    return {"accounts": statuses, "created_count": len(created), "backend_authentication": "passed",
            "borrower_lender_authorization": "passed", "admin_authorization": "passed",
            "unrelated_records_unchanged": True, "intended_project_verified": True,
            "razorpay_test_mode": True, "identities": identities}


def cleanup(engine, metadata, apply):
    manifest = read_manifest()
    require(manifest is not None and manifest.get("project") == EXPECTED_PROJECT,
            "cleanup_requires_original_private_manifest")
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL lock_timeout='5s'")
        connection.exec_driver_sql("SET LOCAL statement_timeout='30s'")
        # Freeze all relevant rows while discovering/deleting dependencies. Locks
        # do not bypass FKs, RLS, or append-only financial guards.
        for table in sorted(metadata.tables.values(), key=lambda t: t.name):
            name = connection.dialect.identifier_preparer.quote(table.name)
            connection.exec_driver_sql(f"LOCK TABLE public.{name} IN SHARE ROW EXCLUSIVE MODE")
        plan = build_cleanup_plan(connection, metadata, manifest["created"])
        if apply:
            execute_cleanup(connection, metadata, plan)
    if apply:
        manifest["state"] = "cleaned"
        write_private(MANIFEST, manifest)
    return {"cleanup": "executed" if apply else "preview_only",
            "scoped_records": {name: len(ids) for name, ids in plan.items()},
            "financial_history_policy": "retain_and_block_cleanup", "external_files_deleted": False}


def main():
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    require(not (args.cleanup and args.verify), "cleanup_and_login_verification_are_separate")
    from sqlalchemy import MetaData, create_engine
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.models import User

    settings = get_settings()
    url = validate_target(settings)
    engine = create_engine(url, hide_parameters=True, echo=False,
                           connect_args={"connect_timeout": 15, "sslmode": "require"},
                           isolation_level="REPEATABLE READ")
    try:
        with engine.connect() as connection:
            require(connection.connection.driver_connection.info.ssl_in_use, "encrypted_database_connection_required")
            metadata = MetaData(schema="public")
            metadata.reflect(bind=connection)
            require(set(User.__table__.columns.keys()).issubset(metadata.tables["public.users"].c.keys()),
                    "existing_user_schema_mismatch_no_migration_permitted")
        if args.cleanup:
            result = cleanup(engine, metadata, args.apply)
        else:
            records = inputs()
            result = provision(engine, metadata, records, args.apply)
            if args.verify:
                with Session(engine) as db:
                    identities = check_authentication(db, records)
                result["port_8000"] = check_port_8000(records, identities)
                result["backend_authentication"] = "passed"
                result["borrower_lender_authorization"] = "passed"
                result["admin_authorization"] = "passed"
        result.pop("identities", None)
        if args.cleanup:
            destination = PRIVATE / ("shared-cleanup.json" if args.apply else "shared-cleanup-preview.json")
        elif not args.apply and not args.verify:
            destination = PRIVATE / "shared-preflight.json"
        else:
            destination = REPORT
        write_private(destination, result)
        print(json.dumps(result, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except ProvisioningError as exc:
        print("Provisioning stopped safely: " + str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        # Never emit SQL, connection URLs, parameters, request bodies or tokens.
        print("Provisioning stopped safely (" + type(exc).__name__ + "); sensitive details suppressed.", file=sys.stderr)
        sys.exit(1)
