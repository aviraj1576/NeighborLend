from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

RentalID = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")]
Stage = Literal["before", "after"]
State = Literal["created", "queued", "processing", "completed", "failed", "cancelled"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = "1.0"


class Evidence(Contract):
    id: UUID
    rental_id: RentalID
    uploader_role: Literal["lender", "borrower"]
    stage: Stage
    viewpoint: str | None = Field(default=None, max_length=80)
    capture_timestamp: datetime | None = None
    metadata_verified: Literal[False] = False
    content_type: Literal["image/jpeg", "image/png"]
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    byte_size: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    uploaded_at: datetime
    validation_status: Literal["validated", "invalid"] = "validated"


class StoredEvidence(Evidence):
    storage_ref: str
    normalized_sha256: str
    uploader_subject: str


class InspectionCreate(Contract):
    rental_id: RentalID
    reference_ids: list[UUID] = Field(min_length=1, max_length=20)
    return_ids: list[UUID] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_evidence(self):
        ids = self.reference_ids + self.return_ids
        if len(set(ids)) != len(ids):
            raise ValueError("Evidence IDs must be unique across both sets")
        return self


class Inspection(InspectionCreate):
    id: UUID
    status: State = "created"
    created_at: datetime
    completed_at: datetime | None = None
    pipeline_version: str = "phase-1-unavailable"
    result_status: Literal["unavailable", "pending", "inconclusive", "review_required"] = (
        "unavailable"
    )
    error_code: str | None = None


class Box(Contract):
    """Normalized coordinates in the cited image's orientation-corrected frame."""

    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    x2: float = Field(ge=0, le=1)
    y2: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def ordered(self):
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("Localization must have positive area")
        return self


class Finding(Contract):
    suspected_damage: Literal["scratch", "crack", "dent", "missing_component", "other", "uncertain"]
    severity: Literal["minor", "moderate", "severe", "uncertain"]
    affected_region: str
    reference_ids: list[UUID] = Field(min_length=1)
    return_ids: list[UUID] = Field(min_length=1)
    localization: dict[UUID, Box] = Field(default_factory=dict)
    supporting_observations: list[str] = Field(min_length=1)
    contradictory_observations: list[str] = Field(default_factory=list)
    comparison_limitations: list[str] = Field(default_factory=list)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def cited_localizations(self):
        if not set(self.localization).issubset(set(self.reference_ids + self.return_ids)):
            raise ValueError("Localization must cite supporting evidence")
        return self


class Health(BaseModel):
    status: Literal["ok"] = "ok"


class Ready(BaseModel):
    status: Literal["ready"] = "ready"
    pipeline: Literal["unavailable"] = "unavailable"


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
    request_id: str
