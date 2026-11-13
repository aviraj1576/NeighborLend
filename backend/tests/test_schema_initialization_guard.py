"""Generic initialization must reject hosted Supabase before any DDL or connection."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from test_listing_conversations import history
from test_razorpay_escrow import flow as payment_flow
from test_razorpay_escrow import fund

import app.database as database
import app.main as main
from app.config import Settings
from app.services import conversation_migrations, payment_migrations

flow = payment_flow

DIRECT = "postgresql+psycopg2://fixture:synthetic-password@db.fixture.supabase.co/postgres"
POOLER = (
    "postgresql+psycopg2://postgres.fixture:synthetic-password"
    "@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"
)
HOSTED_URLS = [
    DIRECT,
    POOLER,
    POOLER.replace(":5432/", ":6543/"),
    DIRECT.replace("db.fixture.supabase.co", "DB.FIXTURE.SUPABASE.CO."),
    "postgresql+psycopg2://fixture:synthetic-password@localhost/postgres"
    "?host=aws-0-ap-southeast-1.pooler.supabase.com",
    "postgresql+psycopg2://fixture:synthetic-password@/postgres"
    "?host=db.fixture.supabase.co",
    "postgresql+psycopg2://fixture:synthetic-password@/postgres"
    "?host=localhost&host=db.fixture.supabase.co:5432",
]


def forbid_call(label):
    return Mock(side_effect=AssertionError(label + " must not run for a hosted target"))


@pytest.mark.parametrize("url", HOSTED_URLS)
@pytest.mark.parametrize("auto_migrate", [False, True])
@pytest.mark.parametrize("explicit_target", [False, True])
def test_direct_helper_rejects_hosted_target_before_all_ddl(
    url, auto_migrate, explicit_target, monkeypatch
):
    target = create_engine(url)
    try:
        begin = forbid_call("engine.begin")
        connect = forbid_call("engine.connect")
        payments = forbid_call("financial migrations")
        conversations = forbid_call("conversation migrations")
        monkeypatch.setattr(target, "begin", begin)
        monkeypatch.setattr(target, "connect", connect)
        monkeypatch.setattr(payment_migrations, "migrate_payments", payments)
        monkeypatch.setattr(conversation_migrations, "migrate_conversations", conversations)
        monkeypatch.setattr(database.settings, "auto_migrate", auto_migrate)
        if not explicit_target:
            monkeypatch.setattr(database, "engine", target)

        with pytest.raises(RuntimeError, match="hosted Supabase") as failure:
            database.migrate_schema(target if explicit_target else None)

        assert "synthetic-password" not in str(failure.value)
        for blocked in (begin, connect, payments, conversations):
            blocked.assert_not_called()
    finally:
        target.dispose()


@pytest.mark.parametrize("url", [DIRECT, POOLER, HOSTED_URLS[4]])
@pytest.mark.parametrize("auto_migrate", [False, True])
def test_startup_blocks_hosted_ddl_but_allows_normal_nonmigrating_startup(
    url, auto_migrate, monkeypatch, tmp_path
):
    target = create_engine(url)
    try:
        create_all = forbid_call("metadata.create_all")
        migrate = forbid_call("migrate_schema")
        begin = forbid_call("engine.begin")
        connect = forbid_call("engine.connect")
        monkeypatch.setattr(main, "engine", target)
        monkeypatch.setattr(main.Base.metadata, "create_all", create_all)
        monkeypatch.setattr(main, "migrate_schema", migrate)
        monkeypatch.setattr(target, "begin", begin)
        monkeypatch.setattr(target, "connect", connect)
        monkeypatch.setattr(
            main,
            "settings",
            Settings(
                _env_file=None,
                app_env="test",
                auto_migrate=auto_migrate,
                payment_provider="disabled",
                payment_demo_mode=False,
                upload_dir=str(tmp_path / "uploads"),
            ),
        )

        if auto_migrate:
            with pytest.raises(RuntimeError, match="hosted Supabase"):
                with TestClient(main.app):
                    pytest.fail("Hosted generic initialization was allowed")
            assert not (tmp_path / "uploads").exists()
        else:
            with TestClient(main.app):
                pass  # Startup is permitted; no route or database request is made.

        for blocked in (create_all, migrate, begin, connect):
            blocked.assert_not_called()
    finally:
        target.dispose()


@pytest.mark.parametrize(
    "url",
    [
        "sqlite://",
        "postgresql+psycopg2://postgres@127.0.0.1/neighborlend_test_guard",
        "postgresql+psycopg2://postgres@localhost/neighborlend_test_guard",
        "postgresql+psycopg2://postgres@db/neighborlend",
        "postgresql+psycopg2://postgres@supabase.com.example.invalid/neighborlend",
    ],
)
def test_guard_preserves_sqlite_loopback_and_other_non_supabase_targets(url):
    target = create_engine(url)
    try:
        database.require_generic_schema_target_allowed(target)
    finally:
        target.dispose()


@pytest.mark.parametrize("flow", ["mock", "postgres"], indirect=True)
def test_local_automatic_startup_preserves_funded_rental_history(flow, monkeypatch):
    fund(flow)  # Synthetic provider and this fixture's disposable database only.
    before = history(flow)
    target = flow["factory"].kw["bind"]
    monkeypatch.setattr(database, "engine", target)
    monkeypatch.setattr(main, "engine", target)
    monkeypatch.setattr(main, "settings", main.settings.model_copy(update={"auto_migrate": True}))

    with TestClient(main.app) as client:
        assert client.get("/api/health").status_code == 200

    assert history(flow) == before
