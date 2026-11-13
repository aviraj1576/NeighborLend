"""The local demo seeder must never overwrite an existing database."""

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from uuid import uuid4


def test_demo_seed_refuses_existing_database_and_requires_explicit_mode():
    root = Path(__file__).resolve().parents[1]
    target = root / ".payment-demo" / f"test-{uuid4().hex}.sqlite3"
    env = os.environ.copy()
    env.update(
        DATABASE_URL=f"sqlite:///{target.as_posix()}",
        APP_ENV="demo",
        PAYMENT_PROVIDER="mock",
        PAYMENT_DEMO_MODE="true",
        PAYMENT_DEMO_PASSWORD="synthetic-test-password-only",
        PYTHONDONTWRITEBYTECODE="1",
    )
    command = [sys.executable, "-B", "scripts/create_payment_demo.py"]

    def run():
        return subprocess.run(
            command, cwd=root, env=env, capture_output=True, text=True, timeout=30
        )

    try:
        env["PAYMENT_DEMO_MODE"] = "false"
        denied = run()
        assert denied.returncode != 0 and "Explicit local mock" in denied.stderr
        assert not target.exists()
        env["PAYMENT_DEMO_MODE"] = "true"
        seeded = run()
        assert seeded.returncode == 0, seeded.stderr
        before = target.read_bytes()
        with closing(sqlite3.connect(target)) as db:
            assert db.execute("SELECT COUNT(*) FROM users WHERE is_verified=1").fetchone()[0] == 3
            assert db.execute("SELECT COUNT(*) FROM users WHERE is_admin=1").fetchone()[0] == 1
            assert db.execute(
                "SELECT price_per_day, security_deposit FROM listings"
            ).fetchone() == (200, 500)
            assert db.execute("SELECT COUNT(*) FROM rental_bookings").fetchone()[0] == 0
        repeated = run()
        assert repeated.returncode != 0 and "NEW SQLite database" in repeated.stderr
        assert target.read_bytes() == before
        assert env["PAYMENT_DEMO_PASSWORD"] not in seeded.stdout
    finally:
        target.unlink(missing_ok=True)
