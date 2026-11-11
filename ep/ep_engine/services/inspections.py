from datetime import UTC, datetime
from uuid import uuid4

from ep_engine.core.exceptions import EPError
from ep_engine.schemas.models import Inspection


class InspectionService:
    def __init__(self, repository, storage):
        self.repository = repository
        self.storage = storage

    def create(self, request, grant):
        grant.authorize(request.rental_id)
        with self.repository.transaction() as connection:
            for stage, ids in (("before", request.reference_ids), ("after", request.return_ids)):
                for evidence_id in ids:
                    try:
                        evidence = self.repository.get_evidence(str(evidence_id), connection)
                    except EPError as exc:
                        raise EPError(
                            422, "invalid_evidence", "Evidence selection is invalid"
                        ) from exc
                    if evidence.rental_id != request.rental_id or evidence.stage != stage:
                        raise EPError(422, "invalid_evidence", "Evidence selection is invalid")
                    if evidence.validation_status != "validated":
                        raise EPError(409, "integrity_failure", "Evidence is invalid")
                    self.storage.verified_read(str(evidence.id), "original", evidence.sha256)
                    self.storage.verified_read(str(evidence.id), "png", evidence.normalized_sha256)
            record = Inspection(**request.model_dump(), id=uuid4(), created_at=datetime.now(UTC))
            self.repository.insert_inspection(connection, record)
        return record

    def read(self, inspection_id, grant):
        record = self.repository.get_inspection(str(inspection_id))
        grant.authorize(record.rental_id)
        return record
