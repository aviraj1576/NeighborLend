import asyncio
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import text

from app.database import SessionLocal, engine
from app.models import DamageCheckRecord
from app.services.damage_storage import HostDamageStorage
from damage_check.schemas import CheckRecord


def _record():
    return CheckRecord(
        id=str(uuid4()),
        request_id=None,
        lender_id="lender",
        borrower_id="borrower",
    )


def test_worker_write_can_commit_while_request_session_has_read_transaction():
    assert engine.dialect.name == "sqlite"
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
    with SessionLocal() as request_session:
        request_session.execute(text("SELECT count(*) FROM damage_check_records")).scalar()
        record = _record()
        asyncio.run(asyncio.to_thread(HostDamageStorage().save_check, record))

    with SessionLocal() as verify_session:
        assert verify_session.get(DamageCheckRecord, record.id) is not None


def test_concurrent_worker_writes_are_serialized_for_sqlite():
    storage = HostDamageStorage()
    records = [_record() for _ in range(12)]
    with ThreadPoolExecutor(max_workers=8) as workers:
        list(workers.map(storage.save_check, records))

    with SessionLocal() as db:
        assert all(db.get(DamageCheckRecord, record.id) is not None for record in records)
