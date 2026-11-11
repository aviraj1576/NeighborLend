import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AssessmentContract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class AssessmentOptions(AssessmentContract):
    allow_external: bool = False
    max_candidates: int = Field(default=4, ge=1, le=8)
    max_pairs: int = Field(default=4, ge=1, le=4)
    image_side: int = Field(default=512, ge=128, le=768)


class Observation(AssessmentContract):
    candidate_id: UUID
    status: Literal[
        "possible_visible_damage", "no_visible_change", "visual_artifact", "insufficient_evidence"
    ]
    damage_type: Literal["scratch", "crack", "dent", "missing_component", "other", "uncertain"] = (
        "uncertain"
    )
    affected_region: str = Field(min_length=1, max_length=200)
    evidence_ids: list[UUID] = Field(min_length=2, max_length=2)
    artifact_ids: list[UUID] = Field(min_length=2, max_length=16)
    explanation: str = Field(min_length=1, max_length=1500)
    uncertainty: str = Field(min_length=1, max_length=600)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def conservative(self):
        if len(set(self.evidence_ids)) != 2 or len(set(self.artifact_ids)) != len(
            self.artifact_ids
        ):
            raise ValueError("Duplicate evidence citations")
        if self.status != "possible_visible_damage" and self.damage_type != "uncertain":
            raise ValueError("A non-damage observation cannot claim a defect type")
        return self


def digest_package(package):
    content = package.model_dump(mode="json")
    # Loading a pre-2.1 archive injects new schema defaults. Preserve the digest
    # already bound to its assessment job, but NEVER discard non-default evidence.
    pair_defaults = {
        "geometry_model": "homography",
        "source_coverage": 0,
        "target_coverage": 0,
        "symmetric_reprojection_error": None,
    }
    legacy = (
        "algorithm_revision" not in package.models
        and not package.boundary_changes
        and all(not q.recommendations for q in package.quality)
        and all(not s.target_support for s in package.segmentation)
        and all(
            all(getattr(p, key) == value for key, value in pair_defaults.items())
            for p in package.pairs
        )
    )
    if legacy:
        content.pop("boundary_changes")
        for quality in content["quality"]:
            quality.pop("recommendations")
        for segment in content["segmentation"]:
            segment.pop("target_support")
        for pair in content["pairs"]:
            for key in pair_defaults:
                pair.pop(key)
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


class ProviderReply(AssessmentContract):
    observations: list[Observation] = Field(min_length=1, max_length=8)
    limitations: list[str] = Field(default_factory=list, max_length=12)


class Usage(AssessmentContract):
    input_tokens: int | None = Field(default=None, ge=0, le=10_000_000)
    output_tokens: int | None = Field(default=None, ge=0, le=10_000_000)


class AssessmentMetrics(Usage):
    attempts: int = Field(default=0, ge=0, le=3)
    elapsed_seconds: float = Field(default=0, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    images_sent: int = Field(default=0, ge=0, le=16)
    image_bytes: int = Field(default=0, ge=0, le=8_000_000)


class AssessmentReport(AssessmentContract):
    schema_version: Literal["4.0"] = "4.0"
    pipeline_version: Literal["ep-assessment-4.0"] = "ep-assessment-4.0"
    cv_run_id: UUID
    inspection_id: UUID
    cv_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_hashes: dict[UUID, str]
    status: Literal["human_review_required", "no_visible_change", "inconclusive", "partial"]
    provider: str
    model: str
    mocked: bool
    cv_model_adapter: str
    selected_candidates: list[UUID] = Field(default_factory=list)
    unassessed_candidates: list[UUID] = Field(default_factory=list)
    findings: list[Observation] = Field(default_factory=list)
    assessed_pairs: list[tuple[UUID, UUID]] = Field(default_factory=list)
    stage_statuses: list[str] = Field(default_factory=list)
    limitations: list[str]
    error_code: str | None = None
    metrics: AssessmentMetrics = Field(default_factory=AssessmentMetrics)
    physical_identity_verified: Literal[False] = False
    human_review_required: Literal[True] = True
    payment_action: Literal["none"] = "none"

    @model_validator(mode="after")
    def consistent(self):
        selected = set(self.selected_candidates)
        if len(selected) != len(self.selected_candidates) or selected & set(
            self.unassessed_candidates
        ):
            raise ValueError("Invalid candidate coverage")
        if any(row.candidate_id not in selected for row in self.findings):
            raise ValueError("Unselected finding")
        if self.status == "no_visible_change" and (
            self.findings or selected or self.unassessed_candidates
        ):
            raise ValueError("No-change result contradicts candidate coverage")
        if self.error_code and (self.findings or self.status != "inconclusive"):
            raise ValueError("Failure cannot produce a definitive result")
        return self
