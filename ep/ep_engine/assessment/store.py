from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from ep_engine.assessment.contracts import AssessmentContract, AssessmentOptions, AssessmentReport
from ep_engine.config import EP_ROOT
from ep_engine.core.exceptions import EPError
from ep_engine.cv.concurrency import worker_guard
from ep_engine.storage.repository import Repository


class AssessmentJob(AssessmentContract):
    id: UUID
    cv_run_id: UUID
    inspection_id: UUID
    rental_id: str
    cv_digest: str
    provider_key: str
    options: AssessmentOptions
    status: Literal["queued", "processing", "completed", "failed", "cancelled"] = "queued"
    created_at: datetime
    finished_at: datetime | None = None
    error_code: str | None = None


class AssessmentStore:
    def __init__(self, directory: Path):
        if directory.is_symlink() or not directory.resolve().is_relative_to(EP_ROOT):
            raise EPError(409, "unsafe_storage", "Invalid assessment storage")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = Repository(directory / "assessments.sqlite3")

    def initialize(self):
        with worker_guard(), self.db.transaction() as connection:
            if connection.execute("PRAGMA user_version").fetchone()[0] not in (0, 1):
                raise RuntimeError("Unsupported assessment schema")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS jobs "
                "(id TEXT PRIMARY KEY, owner TEXT NOT NULL, record TEXT NOT NULL, report TEXT)"
            )
            connection.execute("PRAGMA user_version=1")
            for key, text in connection.execute("SELECT id, record FROM jobs").fetchall():
                job = AssessmentJob.model_validate_json(text)
                if job.status == "processing":
                    job.status, job.error_code, job.finished_at = (
                        "failed",
                        "worker_interrupted",
                        datetime.now(UTC),
                    )
                    connection.execute(
                        "UPDATE jobs SET record=? WHERE id=?", (job.model_dump_json(), key)
                    )

    def get(self, key, connection=None):
        if connection is None:
            with self.db.transaction() as connection:
                return self.get(key, connection)
        row = connection.execute(
            "SELECT owner,record,report FROM jobs WHERE id=?", (str(key),)
        ).fetchone()
        if row is None:
            raise EPError(404, "not_found", "Assessment not found")
        return (
            AssessmentJob.model_validate_json(row[1]),
            row[0],
            AssessmentReport.model_validate_json(row[2]) if row[2] else None,
        )

    def create(self, cv_run, digest, owner, options, provider_key):
        with self.db.transaction() as connection:
            pending = 0
            for _key, subject, text in connection.execute("SELECT id,owner,record FROM jobs"):
                job = AssessmentJob.model_validate_json(text)
                if (
                    subject == owner
                    and job.cv_run_id == cv_run.id
                    and job.cv_digest == digest
                    and job.options == options
                    and job.provider_key == provider_key
                    and job.status in ("queued", "processing", "completed")
                ):
                    return job
                pending += job.status in ("queued", "processing")
            if pending >= 4:
                raise EPError(429, "queue_limit", "Assessment queue is full")
            job = AssessmentJob(
                id=uuid4(),
                cv_run_id=cv_run.id,
                inspection_id=cv_run.inspection_id,
                rental_id=cv_run.rental_id,
                cv_digest=digest,
                options=options,
                provider_key=provider_key,
                created_at=datetime.now(UTC),
            )
            connection.execute(
                "INSERT INTO jobs VALUES (?,?,?,NULL)", (str(job.id), owner, job.model_dump_json())
            )
            return job

    def claim(self, key):
        with self.db.transaction() as connection:
            job, _, _ = self.get(key, connection)
            if job.status != "queued":
                raise EPError(409, "invalid_transition", "Assessment cannot start")
            if any(
                AssessmentJob.model_validate_json(row[0]).status == "processing"
                for row in connection.execute("SELECT record FROM jobs")
            ):
                raise EPError(409, "worker_busy", "Assessment worker is busy")
            job.status = "processing"
            connection.execute(
                "UPDATE jobs SET record=? WHERE id=?", (job.model_dump_json(), str(job.id))
            )
            return job

    def terminate(self, key, status, error=None):
        with self.db.transaction() as connection:
            job, _, _ = self.get(key, connection)
            if job.status not in ("queued", "processing") or status not in ("failed", "cancelled"):
                raise EPError(409, "invalid_transition", "Assessment is already terminal")
            job.status, job.error_code, job.finished_at = status, error, datetime.now(UTC)
            connection.execute(
                "UPDATE jobs SET record=? WHERE id=?", (job.model_dump_json(), str(job.id))
            )
            return job

    def finish(self, key, report):
        with self.db.transaction() as connection:
            job, _, _ = self.get(key, connection)
            if job.status != "processing":
                raise EPError(409, "invalid_transition", "Assessment cannot be committed")
            job.status, job.finished_at = "completed", datetime.now(UTC)
            connection.execute(
                "UPDATE jobs SET record=?, report=? WHERE id=?",
                (job.model_dump_json(), report.model_dump_json(), str(job.id)),
            )
            return job
