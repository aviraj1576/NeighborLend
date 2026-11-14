"""Storage boundary. The host app implements StorageBackend on top of its own
database and Supabase bucket; LocalStorage is for standalone development."""
import os
import re
import tempfile
from pathlib import Path
from typing import List, Optional, Protocol, Tuple

from ._compat import dump_json, parse_json
from .schemas import PHASES, VIEWS, CheckRecord


class StorageBackend(Protocol):
    """All methods are synchronous; the service runs them in worker threads.

    A CheckRecord can be stored as one JSON blob (see _compat.dump_json /
    parse_json) or mapped to columns, whichever the host prefers.
    """

    def save_check(self, record: CheckRecord) -> None: ...

    def load_check(self, check_id: str) -> Optional[CheckRecord]: ...

    def save_photo(self, check_id: str, phase: str, view: str,
                   data: bytes, mime: str) -> None: ...

    def load_photo(self, check_id: str, phase: str, view: str) -> Optional[Tuple[bytes, str]]: ...

    def list_photos(self, check_id: str, phase: str) -> List[str]: ...


_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_MIME = {v: k for k, v in _EXT.items()}


class LocalStorage:
    """Filesystem storage: <root>/<check_id>/record.json + photos/<phase>/<view>.<ext>"""

    def __init__(self, root) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, check_id: str) -> Path:
        if not _ID_RE.match(check_id):
            raise ValueError("bad check id")
        return self.root / check_id

    def _atomic_write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def save_check(self, record: CheckRecord) -> None:
        self._atomic_write(self._dir(record.id) / "record.json", dump_json(record).encode("utf-8"))

    def load_check(self, check_id: str) -> Optional[CheckRecord]:
        path = self._dir(check_id) / "record.json"
        if not path.exists():
            return None
        return parse_json(CheckRecord, path.read_text(encoding="utf-8"))

    def save_photo(self, check_id: str, phase: str, view: str, data: bytes, mime: str) -> None:
        if phase not in PHASES or view not in VIEWS:
            raise ValueError("bad phase or view")
        folder = self._dir(check_id) / "photos" / phase
        for old in folder.glob(view + ".*"):
            old.unlink()
        self._atomic_write(folder / (view + _EXT.get(mime, ".bin")), data)

    def load_photo(self, check_id: str, phase: str, view: str) -> Optional[Tuple[bytes, str]]:
        if phase not in PHASES or view not in VIEWS:
            return None
        folder = self._dir(check_id) / "photos" / phase
        for path in folder.glob(view + ".*"):
            return path.read_bytes(), _MIME.get(path.suffix, "application/octet-stream")
        return None

    def list_photos(self, check_id: str, phase: str) -> List[str]:
        if phase not in PHASES:
            return []
        folder = self._dir(check_id) / "photos" / phase
        if not folder.exists():
            return []
        present = {p.stem for p in folder.iterdir() if p.is_file()}
        return [v for v in VIEWS if v in present]
