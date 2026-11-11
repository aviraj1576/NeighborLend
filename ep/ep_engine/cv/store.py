import hashlib
import io
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from PIL import Image, UnidentifiedImageError

from ep_engine.config import EP_ROOT
from ep_engine.core.exceptions import EPError
from ep_engine.cv.concurrency import worker_guard
from ep_engine.cv.contracts import CVContract, CVPackage, RunRequest
from ep_engine.storage.repository import Repository


class RunRecord(CVContract):
    id: UUID
    inspection_id: UUID
    rental_id: str
    status: Literal["queued", "processing", "completed", "failed", "cancelled"] = "queued"
    created_at: datetime
    finished_at: datetime | None = None
    error_code: str | None = None
    request: RunRequest


def cleanup(root, path):
    root, path = root.resolve(), path.resolve()
    if not path.is_relative_to(root) or path == root:
        raise EPError(409, "artifact_path", "Unsafe cleanup path")
    if path.exists():
        shutil.rmtree(path)


class CVStore:
    """Separate versioned CV database; Phase 1 schema/state semantics stay unchanged."""

    def __init__(self, root: Path):
        if root.is_symlink() or not root.resolve().is_relative_to(EP_ROOT):
            raise EPError(409, "artifact_path", "Invalid CV storage root")
        self.root = root.resolve()
        self.work = self.root / "work"
        self.artifacts = self.root / "artifacts"
        for path in (self.work, self.artifacts):
            if path.is_symlink():
                raise EPError(409, "artifact_path", "Invalid CV directory")
            path.mkdir(parents=True, exist_ok=True)
        self.db = Repository(self.root / "cv.sqlite3")

    def initialize(self):
        with worker_guard():
            self._initialize()

    def _initialize(self):
        with self.db.transaction() as connection:
            if connection.execute("PRAGMA user_version").fetchone()[0] not in (0, 1):
                raise RuntimeError("Unsupported CV schema version")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, record TEXT NOT NULL, "
                "subject TEXT NOT NULL, result TEXT)"
            )
            connection.execute("PRAGMA user_version=1")
            rows = connection.execute("SELECT id, record, result FROM runs").fetchall()
            completed = set()
            for key, record, result in rows:
                run = RunRecord.model_validate_json(record)
                if run.status == "processing":
                    run.status, run.error_code, run.finished_at = (
                        "failed",
                        "worker_interrupted",
                        datetime.now(UTC),
                    )
                    connection.execute(
                        "UPDATE runs SET record=? WHERE id=?", (run.model_dump_json(), key)
                    )
                if run.status == "completed":
                    try:
                        self.verify_package_files(key, CVPackage.model_validate_json(result))
                        completed.add(key)
                    except (EPError, ValueError):
                        run.status, run.error_code = "failed", "artifact_integrity"
                        connection.execute(
                            "UPDATE runs SET record=?, result=NULL WHERE id=?",
                            (run.model_dump_json(), key),
                        )
            for path in self.artifacts.iterdir():
                if path.name not in completed:
                    cleanup(self.artifacts, path)
            for path in self.work.iterdir():
                cleanup(self.work, path)

    def get(self, run_id, connection=None):
        if connection is None:
            with self.db.transaction() as connection:
                return self.get(run_id, connection)
        row = connection.execute(
            "SELECT record, subject, result FROM runs WHERE id=?", (str(run_id),)
        ).fetchone()
        if row is None:
            raise EPError(404, "not_found", "CV run not found")
        return (
            RunRecord.model_validate_json(row[0]),
            row[1],
            CVPackage.model_validate_json(row[2]) if row[2] else None,
        )

    def create(self, inspection, request, subject):
        record = RunRecord(
            id=uuid4(),
            inspection_id=inspection.id,
            rental_id=inspection.rental_id,
            created_at=datetime.now(UTC),
            request=request,
        )
        with self.db.transaction() as connection:
            pending = sum(
                RunRecord.model_validate_json(row[0]).status in ("queued", "processing")
                for row in connection.execute("SELECT record FROM runs")
            )
            if pending >= 4:
                raise EPError(429, "queue_limit", "Local CV queue is full")
            connection.execute(
                "INSERT INTO runs VALUES (?, ?, ?, NULL)",
                (str(record.id), record.model_dump_json(), subject),
            )
        return record

    def claim(self, run_id):
        with self.db.transaction() as connection:
            run, _, _ = self.get(run_id, connection)
            if run.status != "queued":
                raise EPError(409, "invalid_transition", "CV run cannot be started")
            if any(
                RunRecord.model_validate_json(row[0]).status == "processing"
                for row in connection.execute("SELECT record FROM runs")
            ):
                raise EPError(409, "worker_busy", "Only one CV run may execute at a time")
            run.status = "processing"
            connection.execute(
                "UPDATE runs SET record=? WHERE id=?", (run.model_dump_json(), str(run.id))
            )
            return run

    def terminate(self, run_id, status, code=None):
        with self.db.transaction() as connection:
            run, _, _ = self.get(run_id, connection)
            if run.status not in ("queued", "processing") or status not in ("cancelled", "failed"):
                raise EPError(409, "invalid_transition", "CV run is already terminal")
            run.status, run.error_code, run.finished_at = status, code, datetime.now(UTC)
            connection.execute(
                "UPDATE runs SET record=? WHERE id=?", (run.model_dump_json(), str(run.id))
            )
            return run

    def finish(self, run_id, package, output):
        self.verify_package_files(run_id, package, output)
        target = self.artifacts / str(UUID(str(run_id)))
        promoted = False
        try:
            with self.db.transaction() as connection:
                run, _, _ = self.get(run_id, connection)
                if run.status != "processing" or target.exists():
                    raise EPError(409, "invalid_transition", "CV run cannot be committed")
                try:
                    output.rename(target)
                    promoted = True
                except PermissionError as exc:
                    if os.name != "nt" or getattr(exc, "winerror", None) not in {5, 32, 33}:
                        raise
                    # Windows can deny directory rename while another process
                    # holds a directory handle. No retries or relaxed ACLs: copy
                    # only the verified bounded manifest into a new private dir,
                    # reverify it, and publish through the SAME DB transaction.
                    target.mkdir(exist_ok=False)
                    promoted = True
                    for artifact in package.artifacts:
                        name = f"{artifact.id}.png"
                        with (target / name).open("xb") as stream:
                            stream.write((output / name).read_bytes())
                            stream.flush()
                            os.fsync(stream.fileno())
                    self.verify_package_files(run_id, package, target)
                run.status, run.finished_at = "completed", datetime.now(UTC)
                connection.execute(
                    "UPDATE runs SET record=?, result=? WHERE id=?",
                    (run.model_dump_json(), package.model_dump_json(), str(run.id)),
                )
        except BaseException:
            if promoted:
                cleanup(self.artifacts, target)
            raise
        return run

    def verify_package_files(self, run_id, package, directory=None):
        directory = directory or self.artifacts / str(UUID(str(run_id)))
        if directory.is_symlink() or not directory.resolve().is_relative_to(self.root):
            raise EPError(409, "artifact_path", "Unsafe artifact location")
        expected = {f"{row.id}.png" for row in package.artifacts}
        if not directory.is_dir() or {p.name for p in directory.iterdir()} != expected:
            raise EPError(409, "artifact_integrity", "Artifact manifest mismatch")
        total = 0
        for row in package.artifacts:
            path = directory / f"{row.id}.png"
            if path.is_symlink() or path.stat().st_size != row.byte_size:
                raise EPError(409, "artifact_integrity", "Invalid artifact size or path")
            total += row.byte_size
            data = path.read_bytes()
            if total > 32_000_000 or hashlib.sha256(data).hexdigest() != row.sha256:
                raise EPError(409, "artifact_integrity", "Artifact integrity check failed")
            try:
                with Image.open(io.BytesIO(data)) as image:
                    if image.format != "PNG" or image.size != (row.width, row.height):
                        raise ValueError("Artifact image metadata mismatch")
                    image.verify()
            except (OSError, ValueError, UnidentifiedImageError) as exc:
                raise EPError(409, "artifact_integrity", "Invalid PNG artifact") from exc
