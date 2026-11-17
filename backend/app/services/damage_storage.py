"""StorageBackend adapter for the damage_check module.

Check records (one JSON blob each) live in the damage_check_records table.
Photo bytes live in the damage_check_photos table (the server disk is ephemeral);
older photos on local disk under backend/damage_data/ are still read. They are deliberately
NOT under uploads/, which is served publicly without authentication.
"""
from pathlib import Path
from threading import Lock
from contextlib import nullcontext

from damage_check._compat import dump_json, parse_json
from damage_check.schemas import PHASES, VIEWS, CheckRecord
from damage_check.storage import LocalStorage

from app.database import SessionLocal, engine
from app.models import DamageCheckPhoto, DamageCheckRecord

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

    # Photo bytes are stored in the database: the server disk is wiped on every
    # restart/redeploy, which made lender photos and borrower ghosts disappear.
    # Photos written to disk by older versions are still read as a fallback.
    def save_photo(self, check_id, phase, view, data, mime) -> None:
        if phase not in PHASES or view not in VIEWS:
            raise ValueError("bad phase or view")
        lock = _SQLITE_CHECK_WRITE_LOCK if engine.dialect.name == "sqlite" else nullcontext()
        with lock:
            with SessionLocal() as db:
                row = db.get(DamageCheckPhoto, (check_id, phase, view))
                if row is None:
                    row = DamageCheckPhoto(check_id=check_id, phase=phase, view=view, mime=mime, data=data)
                    db.add(row)
                else:
                    row.mime, row.data = mime, data
                db.commit()

    def load_photo(self, check_id, phase, view):
        with SessionLocal() as db:
            row = db.get(DamageCheckPhoto, (check_id, phase, view))
            if row is not None:
                return bytes(row.data), row.mime
        try:
            return self._photos.load_photo(check_id, phase, view)
        except (OSError, ValueError):
            return None

    def list_photos(self, check_id, phase):
        if phase not in PHASES:
            return []
        with SessionLocal() as db:
            present = {
                v for (v,) in db.query(DamageCheckPhoto.view)
                .filter(DamageCheckPhoto.check_id == check_id, DamageCheckPhoto.phase == phase)
                .all()
            }
        try:
            present |= set(self._photos.list_photos(check_id, phase))
        except (OSError, ValueError):
            pass
        return [v for v in VIEWS if v in present]
