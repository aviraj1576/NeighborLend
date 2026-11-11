import hashlib
import os
from pathlib import Path
from uuid import UUID, uuid4

from ep_engine.config import EP_ROOT
from ep_engine.core.exceptions import EPError


class LocalStorage:
    """Private adapter: opaque keys only; caller owns the upload transaction."""

    def __init__(self, root: Path):
        if (
            root.is_symlink()
            or not root.resolve().is_relative_to(EP_ROOT)
            or root.resolve() == EP_ROOT
        ):
            raise ValueError("Invalid EP private storage root")
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, evidence_id: str, suffix: str) -> Path:
        if suffix not in ("original", "png"):
            raise ValueError("Invalid evidence representation")
        result = self.root / f"{UUID(str(evidence_id))}.{suffix}"
        if result.is_symlink() or not result.resolve().is_relative_to(self.root.resolve()):
            raise EPError(409, "unsafe_storage", "Invalid private storage entry")
        return result

    def write(self, evidence_id: str, original: bytes, normalized: bytes):
        for suffix, content in (("original", original), ("png", normalized)):
            target = self.path(evidence_id, suffix)
            temporary = self.root / f"{uuid4()}.part"
            try:
                with temporary.open("xb") as stream:
                    if os.name != "nt":
                        os.chmod(temporary, 0o600)
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)

    def ensure_unused(self, evidence_id: str):
        # Caller holds the EP database write lock until promotion/metadata commit finish.
        if any(self.path(evidence_id, suffix).exists() for suffix in ("original", "png")):
            raise EPError(409, "identifier_conflict", "Evidence identifier is already allocated")

    def delete(self, evidence_id: str):
        for suffix in ("original", "png"):
            self.path(evidence_id, suffix).unlink(missing_ok=True)

    def verified_read(self, evidence_id: str, suffix: str, expected_hash: str) -> bytes:
        try:
            result = self.path(evidence_id, suffix).read_bytes()
        except FileNotFoundError as exc:
            raise EPError(409, "integrity_failure", "Evidence bytes are unavailable") from exc
        if hashlib.sha256(result).hexdigest() != expected_hash:
            raise EPError(409, "integrity_failure", "Evidence integrity check failed")
        return result

    def check(self):
        probe = self.root / f"{uuid4()}.part"
        try:
            with probe.open("xb") as stream:
                stream.write(b"ready")
        finally:
            probe.unlink(missing_ok=True)
