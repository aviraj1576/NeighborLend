"""Keep backend tests isolated from any database configured in .env."""

import os
import sys
import tempfile
import uuid
from pathlib import Path


_TEST_DATABASE = Path(tempfile.gettempdir()) / f"neighborlend-tests-{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DATABASE.as_posix()}"
# Tests must never call the real vision model, whichever test module imports `app` first.
os.environ.setdefault("DAMAGE_PROVIDER", "mock")


def pytest_sessionfinish(session, exitstatus):
    database_module = sys.modules.get("app.database")
    if database_module is not None:
        database_module.engine.dispose()
    _TEST_DATABASE.unlink(missing_ok=True)
