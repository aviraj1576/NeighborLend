import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from ep_engine.config import EP_ROOT
from ep_engine.core.exceptions import EPError
from ep_engine.schemas.models import Inspection, StoredEvidence

TRANSITIONS = {
    "created": {"queued", "cancelled", "failed"},
    "queued": {"processing", "cancelled", "failed"},
    "processing": {"completed", "failed", "cancelled"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}


class Repository:
    def __init__(self, path: Path):
        if path.is_symlink() or not path.resolve().parent.is_relative_to(EP_ROOT):
            raise ValueError("Invalid EP database path")
        self.path = path.resolve()

    @contextmanager
    def transaction(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self):
        with self.transaction() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError("Unsupported EP schema version")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS evidence ("
                "id TEXT PRIMARY KEY, rental TEXT NOT NULL, stage TEXT NOT NULL, "
                "subject TEXT NOT NULL, digest TEXT NOT NULL, record TEXT NOT NULL, "
                "UNIQUE(rental, stage, subject, digest))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS inspections (id TEXT PRIMARY KEY, record TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS inspection_evidence ("
                "inspection_id TEXT REFERENCES inspections(id), "
                "evidence_id TEXT REFERENCES evidence(id), PRIMARY KEY(inspection_id, evidence_id))"
            )
            connection.execute("PRAGMA user_version=1")

    def check(self):
        with self.transaction() as connection:
            connection.execute("SELECT count(*) FROM evidence").fetchone()

    def duplicate(self, connection, rental, stage, subject, digest):
        row = connection.execute(
            "SELECT record FROM evidence WHERE rental=? AND stage=? AND subject=? AND digest=?",
            (rental, stage, subject, digest),
        ).fetchone()
        return StoredEvidence.model_validate_json(row[0]) if row else None

    def insert_evidence(self, connection, evidence: StoredEvidence):
        connection.execute(
            "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(evidence.id),
                evidence.rental_id,
                evidence.stage,
                evidence.uploader_subject,
                evidence.sha256,
                evidence.model_dump_json(),
            ),
        )

    def ensure_evidence_id_unused(self, connection, evidence_id: str):
        if connection.execute("SELECT 1 FROM evidence WHERE id=?", (evidence_id,)).fetchone():
            raise EPError(409, "identifier_conflict", "Evidence identifier is already allocated")

    def get_evidence(self, evidence_id: str, connection=None) -> StoredEvidence:
        if connection is None:
            with self.transaction() as connection:
                return self.get_evidence(evidence_id, connection)
        row = connection.execute(
            "SELECT record FROM evidence WHERE id=?", (str(evidence_id),)
        ).fetchone()
        if row is None:
            raise EPError(404, "not_found", "Evidence not found")
        return StoredEvidence.model_validate_json(row[0])

    def get_inspection(self, inspection_id: str, connection=None) -> Inspection:
        if connection is None:
            with self.transaction() as connection:
                return self.get_inspection(inspection_id, connection)
        row = connection.execute(
            "SELECT record FROM inspections WHERE id=?", (str(inspection_id),)
        ).fetchone()
        if row is None:
            raise EPError(404, "not_found", "Inspection not found")
        return Inspection.model_validate_json(row[0])

    def insert_inspection(self, connection, record: Inspection):
        connection.execute(
            "INSERT INTO inspections VALUES (?, ?)", (str(record.id), record.model_dump_json())
        )
        connection.executemany(
            "INSERT INTO inspection_evidence VALUES (?, ?)",
            [(str(record.id), str(key)) for key in record.reference_ids + record.return_ids],
        )

    def transition(self, inspection_id: str, target: str, *, error_code: str | None = None):
        with self.transaction() as connection:
            record = self.get_inspection(inspection_id, connection)
            if target not in TRANSITIONS[record.status]:
                raise EPError(409, "invalid_transition", "Illegal inspection state transition")
            if target == "completed":
                raise EPError(503, "pipeline_unavailable", "Phase 1 cannot complete analysis")
            record.status = target
            record.error_code = error_code
            record.result_status = "unavailable" if target == "failed" else "pending"
            if target in ("failed", "cancelled"):
                record.completed_at = datetime.now(UTC)
            connection.execute(
                "UPDATE inspections SET record=? WHERE id=?",
                (record.model_dump_json(), str(record.id)),
            )
            return record

    def recover(self, storage):
        # The same database write lock serializes startup recovery and in-flight uploads.
        with self.transaction() as connection:
            records = [
                StoredEvidence.model_validate_json(row[0])
                for row in connection.execute("SELECT record FROM evidence")
            ]
            expected = set()
            for record in records:
                for suffix in ("original", "png"):
                    expected.add(f"{record.id}.{suffix}")
                try:
                    storage.verified_read(str(record.id), "original", record.sha256)
                    storage.verified_read(str(record.id), "png", record.normalized_sha256)
                except EPError:
                    record.validation_status = "invalid"
                    connection.execute(
                        "UPDATE evidence SET record=? WHERE id=?",
                        (record.model_dump_json(), str(record.id)),
                    )
            for path in storage.root.iterdir():
                # Dedicated private directory only. Never traverse children or follow links.
                if path.is_file() and path.name not in expected:
                    path.unlink()
            for row in connection.execute("SELECT id, record FROM inspections").fetchall():
                record = Inspection.model_validate_json(row[1])
                if record.status == "processing":
                    record.status = "failed"
                    record.error_code = "restart_interrupted"
                    record.result_status = "unavailable"
                    record.completed_at = datetime.now(UTC)
                    connection.execute(
                        "UPDATE inspections SET record=? WHERE id=?",
                        (record.model_dump_json(), row[0]),
                    )
