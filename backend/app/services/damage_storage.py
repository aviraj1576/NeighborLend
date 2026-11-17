"""StorageBackend adapter for the damage_check module.

Check records (one JSON blob each) live in the damage_check_records table.
Photo bytes live in the same table, one row per photo keyed
``photo:<check_id>:<phase>:<view>``, because the server disk is ephemeral
(wiped on every Render restart/redeploy) and hosted Supabase does not allow
creating new tables at startup. Photos written to local disk by older versions
are still read as a fallback. Photos are deliberately NOT under uploads/, which
is served publicly without authentication.
"""
import base64
import json
from contextlib import nullcontext
from pathlib import Path
from threading import Lock

from damage_check._compat import dump_json, parse_json
from damage_check.schemas import PHASES, VIEWS, CheckRecord
from damage_check.storage import LocalStorage

from app.database import SessionLocal, engine
from app.models import DamageCheckRecord

DAMAGE_DATA_DIR = Path(__file__).resolve().parents[2] / "damage_data"
_SQLITE_CHECK_WRITE_LOCK = Lock()


def _photo_key(check_id: str, phase: str, view: str) -> str:
    return f"photo:{check_id}:{phase}:{view}"


def _write_lock():
    return _SQLITE_CHECK_WRITE_LOCK if engine.dialect.name == "sqlite" else nullcontext()


class HostDamageStorage:
    def __init__(self) -> None:
        self._photos = LocalStorage(DAMAGE_DATA_DIR)

    # The service calls these from worker threads, so each call opens and closes
    # its own session. SQLite permits one writer; serialize check read/modify/
    # write operations so concurrent worker threads cannot race on the same file.
    def save_check(self, record: CheckRecord) -> None:
        with _write_lock():
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
        if phase not in PHASES or view not in VIEWS:
            raise ValueError("bad phase or view")
        payload = json.dumps({"mime": mime, "b64": base64.b64encode(data).decode("ascii")})
        key = _photo_key(check_id, phase, view)
        with _write_lock():
            with SessionLocal() as db:
                row = db.get(DamageCheckRecord, key)
                if row is None:
                    row = DamageCheckRecord(check_id=key)
                    db.add(row)
                row.record_json = payload
                db.commit()

    def load_photo(self, check_id, phase, view):
        if phase not in PHASES or view not in VIEWS:
            return None
        with SessionLocal() as db:
            row = db.get(DamageCheckRecord, _photo_key(check_id, phase, view))
            if row is not None:
                stored = json.loads(row.record_json)
                return base64.b64decode(stored["b64"]), stored["mime"]
        try:
            return self._photos.load_photo(check_id, phase, view)
        except (OSError, ValueError):
            return None

    def list_photos(self, check_id, phase):
        if phase not in PHASES:
            return []
        keys = [_photo_key(check_id, phase, v) for v in VIEWS]
        with SessionLocal() as db:
            found = {
                key for (key,) in db.query(DamageCheckRecord.check_id)
                .filter(DamageCheckRecord.check_id.in_(keys))
                .all()
            }
        present = {v for v in VIEWS if _photo_key(check_id, phase, v) in found}
        try:
            present |= set(self._photos.list_photos(check_id, phase))
        except (OSError, ValueError):
            pass
        return [v for v in VIEWS if v in present]
