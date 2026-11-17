"""StorageBackend adapter for the damage_check module.

Check records (one JSON blob each) live in the damage_check_records table.
Photo bytes live on local disk under backend/damage_data/ and are deliberately
NOT under uploads/, which is served publicly without authentication.
"""
from pathlib import Path
from threading import Lock
from contextlib import nullcontext

from damage_check._compat import dump_json, parse_json
from damage_check.schemas import CheckRecord
from damage_check.storage import LocalStorage

from app.database import SessionLocal, engine
from app.models import DamageCheckRecord

DAMAGE_DATA_DIR = Path(__file__).resolve().parents[2] / "damage_data"
_SQLITE_CHECK_WRITE_LOCK = Lock()


class HostDamageStorage:
    def __init__(self) -> None:
        self._photos = LocalStorage(DAMAGE_DATA_DIR)

    # The service calls these from worker threads, so each call opens and closes
    # its own session. SQLite permits one writer; serialize check read/modify/
    # write operations so concurrent worker threads cannot race on the same file.
    def save_check(self, record: CheckRecord) -> None:
        lock = _SQLITE_CHECK_WRITE_LOCK if engine.dialect.name == "sqlite" else nullcontext()
        with lock:
            with SessionLocal() as db:
                row = db.get(DamageCheckRecord, record.id)
                if row is None:
                    row = DamageCheckRecord(check_id=record.id)
                    db.add(row)
                row.record_json = dump_json(record)
                db.commit()

    def load_check(self, check_id: str):
        db = SessionLocal()
        try:
            row = db.get(DamageCheckRecord, check_id)
            return parse_json(CheckRecord, row.record_json) if row else None
        finally:
            db.close()

    def save_photo(self, check_id, phase, view, data, mime) -> None:
        self._photos.save_photo(check_id, phase, view, data, mime)

    def load_photo(self, check_id, phase, view):
        return self._photos.load_photo(check_id, phase, view)

    def list_photos(self, check_id, phase):
        return self._photos.list_photos(check_id, phase)
