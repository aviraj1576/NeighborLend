from datetime import UTC, datetime
from uuid import uuid4

from ep_engine.core.exceptions import EPError
from ep_engine.schemas.models import StoredEvidence
from ep_engine.services.images import decode_image


class EvidenceService:
    def __init__(self, settings, repository, storage):
        self.settings = settings
        self.repository = repository
        self.storage = storage

    def ingest(self, data, mime, rental_id, stage, grant, viewpoint=None, capture_timestamp=None):
        role = grant.authorize(rental_id, stage)
        decoded = decode_image(data, mime, self.settings)
        evidence_id = str(uuid4())
        record = StoredEvidence(
            id=evidence_id,
            rental_id=rental_id,
            uploader_role=role,
            uploader_subject=grant.subject,
            stage=stage,
            viewpoint=viewpoint,
            capture_timestamp=capture_timestamp,
            content_type=decoded.content_type,
            width=decoded.width,
            height=decoded.height,
            byte_size=len(data),
            sha256=decoded.sha256,
            normalized_sha256=decoded.normalized_sha256,
            uploaded_at=datetime.now(UTC),
            storage_ref=evidence_id,
        )
        owns_files = False
        try:
            with self.repository.transaction() as connection:
                existing = self.repository.duplicate(
                    connection, rental_id, stage, grant.subject, decoded.sha256
                )
                if existing:
                    self.storage.verified_read(str(existing.id), "original", existing.sha256)
                    self.storage.verified_read(str(existing.id), "png", existing.normalized_sha256)
                    if existing.validation_status != "validated":
                        raise EPError(409, "integrity_failure", "Existing evidence is invalid")
                    return existing, False
                self.repository.ensure_evidence_id_unused(connection, evidence_id)
                self.storage.ensure_unused(evidence_id)
                owns_files = True
                self.storage.write(evidence_id, data, decoded.normalized)
                self.repository.insert_evidence(connection, record)
        except BaseException:
            # A crash/power loss here is handled by startup recovery under the same DB lock.
            if owns_files:
                self.storage.delete(evidence_id)
            raise
        return record, True

    def read(self, evidence_id, grant):
        record = self.repository.get_evidence(str(evidence_id))
        grant.authorize(record.rental_id)
        return record

    def content(self, evidence_id, grant):
        record = self.read(evidence_id, grant)
        if record.validation_status != "validated":
            raise EPError(409, "integrity_failure", "Evidence is invalid")
        return self.storage.verified_read(
            str(record.id), "original", record.sha256
        ), record.content_type
