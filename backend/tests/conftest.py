"""Keep backend tests isolated from any database configured in .env."""

import os
import sys
import tempfile
import uuid
import pytest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".test-tools"))


_TEST_DATABASE = Path(tempfile.gettempdir()) / f"neighborlend-tests-{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DATABASE.as_posix()}"
os.environ["APP_ENV"] = "test"
os.environ["PAYMENT_PROVIDER"] = "mock"
os.environ["PAYMENT_DEMO_MODE"] = "true"
os.environ["DEPLOYMENT_EXPOSURE"] = "local"
os.environ["PUBLIC_BASE_URL"] = "http://localhost:8000"
os.environ["CORS_ORIGINS"] = "http://127.0.0.1:5173"
os.environ["JWT_SECRET"] = uuid.uuid4().hex + uuid.uuid4().hex
os.environ["AUTO_MIGRATE"] = "false"
os.environ["RENTAL_EVIDENCE_DIR"] = str(Path(__file__).resolve().parents[1] / ".payment-verification" / "evidence")
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
# Financial regression tests never consume configured external provider credentials.
for _name in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET"):
    # Empty process values also shadow backend/.env; tests must never load local keys.
    os.environ[_name] = ""


def pytest_sessionstart(session):
    # Only this generated test database is initialized. Importing app.main is inert.
    from app.database import Base, engine, migrate_schema
    from app import models  # noqa: F401
    Base.metadata.create_all(engine)
    migrate_schema(engine)


def pytest_sessionfinish(session, exitstatus):
    database_module = sys.modules.get("app.database")
    if database_module is not None:
        database_module.engine.dispose()
    _TEST_DATABASE.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def deny_real_payment_network(monkeypatch):
    # Every provider test must use synthetic transport. A missing stub must fail
    # before contacting Razorpay, even if a developer's machine has credentials.
    def denied(*args, **kwargs):
        raise AssertionError("External payment network is forbidden in regression tests")

    monkeypatch.setattr("app.services.razorpay_service.build_opener", denied)
