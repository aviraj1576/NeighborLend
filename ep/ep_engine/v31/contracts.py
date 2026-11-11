"""The 3.1 envelope retains the strict, backwards-compatible 2.0 CV package."""

from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ep_engine.cv.contracts import CVPackage
from ep_engine.cv.numerics import finite_tree
from ep_engine.schemas.models import Box
from ep_engine.v3.config import V3Config


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Capture(Contract):
    id: UUID
    stage: Literal["before", "after"]
    path: Path
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    normalized_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    target: Box | None = None
    view: str | None = Field(default=None, max_length=128)
    instance_id: str | None = Field(default=None, min_length=1, max_length=80)


class InspectionRequest(Contract):
    inspection_id: UUID
    config: V3Config = Field(default_factory=V3Config)
    evidence: list[Capture] = Field(min_length=2, max_length=12)
    object_metadata: dict[str, str] = Field(default_factory=dict, max_length=20)
    high_resolution_crops: int = Field(default=4, ge=0, le=8)
    surface_observation_budget: int = Field(default=4, ge=0, le=8)

    @model_validator(mode="after")
    def input_collection(self):
        if len({row.id for row in self.evidence}) != len(self.evidence):
            raise ValueError("Duplicate evidence IDs")
        if {row.stage for row in self.evidence} != {"before", "after"}:
            raise ValueError("Both capture stages are required")
        if len(self.evidence) > self.config.max_images:
            raise ValueError("Configured image budget exceeded")
        return self


class IdentityAssessment(Contract):
    before_id: UUID
    after_id: UUID
    status: Literal["identity_unverified"] = "identity_unverified"
    visual_relation: Literal[
        "same_capture",
        "local_visual_consistency",
        "embedding_similarity_only",
        "inconsistent_visual_evidence",
        "insufficient_evidence",
    ]
    physical_identity_verified: Literal[False] = False
    reasons: list[str]


class InstanceAssociation(Contract):
    evidence_id: UUID
    instance_id: str | None
    source: Literal["operator_target_metadata", "unspecified"]
    significant_mask_components: int = Field(ge=0)
    assignment_verified: Literal[False] = False


class ViewAssessment(Contract):
    before_id: UUID
    after_id: UUID
    observation: Literal[
        "not_assessable", "observed_appearance_difference", "no_localized_change_detected"
    ]
    assessable_after_fraction: float = Field(ge=0, le=1)
    unassessed_after_fraction: float = Field(ge=0, le=1)
    sampling_floor_after_source_pixels: float | None = Field(default=None, ge=0)
    localization_uncertainty_after_source_pixels: float | None = Field(default=None, ge=0)
    source_ids: list[UUID] = Field(min_length=2, max_length=2)
    candidate_ids: list[UUID] = Field(default_factory=list)
    boundary_ids: list[UUID] = Field(default_factory=list)
    uncertainty_reasons: list[str]


class CaptureGuidance(Contract):
    source_ids: list[UUID] = Field(min_length=1)
    category: Literal[
        "input_quality",
        "common_surface",
        "identity",
        "geometry",
        "resolution",
        "conflicting_evidence",
        "runtime",
        "instances",
    ]
    reason: str
    recommendation: str


class DetailCrop(Contract):
    before_id: UUID
    after_id: UUID
    candidate_id: UUID
    after_box: Box
    width: int = Field(gt=0, le=1024)
    height: int = Field(gt=0, le=1024)
    sampling_floor_source_pixels: float = Field(ge=2)
    artifact_ids: list[UUID] = Field(min_length=3, max_length=3)
    coordinate_system: Literal["after_source_crop_registered_before"] = (
        "after_source_crop_registered_before"
    )
    interpretation: Literal["detail_for_human_review_only"] = "detail_for_human_review_only"


class SurfaceObservation(Contract):
    before_id: UUID
    after_id: UUID
    scope: Literal["local_correspondence_hull", "original_resolution_tile"]
    after_box: Box
    width: int = Field(gt=0, le=1024)
    height: int = Field(gt=0, le=1024)
    valid_fraction: float = Field(ge=0, le=1)
    assessed_after_mask_fraction: float = Field(ge=0, le=1)
    sampling_floor_source_pixels: float = Field(ge=2)
    registration_uncertainty_source_pixels: float = Field(ge=0)
    appearance_regions: list[Box] = Field(default_factory=list, max_length=20)
    artifact_ids: list[UUID] = Field(min_length=4, max_length=4)
    geometry_support: dict
    interpretation: Literal["localized_appearance_evidence_not_damage"] = (
        "localized_appearance_evidence_not_damage"
    )
    uncertainty_reasons: list[str]


class InspectionReport(Contract):
    schema_version: Literal["3.1"] = "3.1"
    engine_version: Literal["ep-v3.1-advisory"] = "ep-v3.1-advisory"
    inspection_id: UUID
    payment_action: Literal["none"] = "none"
    human_review_required: Literal[True] = True
    physical_identity_verified: Literal[False] = False
    score_interpretation: Literal["uncalibrated_evidence_scores_not_probabilities"] = (
        "uncalibrated_evidence_scores_not_probabilities"
    )
    cv_package: CVPackage
    identity: list[IdentityAssessment]
    instances: list[InstanceAssociation]
    views: list[ViewAssessment]
    possible_damage_hypotheses: list[dict] = Field(default_factory=list, max_length=0)
    detail_crops: list[DetailCrop] = Field(default_factory=list, max_length=8)
    surface_observations: list[SurfaceObservation] = Field(default_factory=list, max_length=8)
    recapture_guidance: list[CaptureGuidance]
    fusion: dict
    runtime: dict
    limitations: list[str]

    @model_validator(mode="after")
    def evidence_integrity(self):
        finite_tree(self.model_dump())
        package = self.cv_package
        if self.inspection_id != package.inspection_id:
            raise ValueError("Inspection identity differs from CV package")
        sources = set(package.source_ids)
        pairs = {(row.before_id, row.after_id) for row in package.pairs}
        for collection in (self.identity, self.views):
            keys = [(row.before_id, row.after_id) for row in collection]
            if len(keys) != len(pairs) or set(keys) != pairs:
                raise ValueError("View/identity coverage differs from CV package")
        if (
            len(self.instances) != len(sources)
            or {r.evidence_id for r in self.instances} != sources
        ):
            raise ValueError("Instance provenance differs from sources")
        candidates = {r.id: r for r in package.candidates}
        boundaries = {r.id: r for r in package.boundary_changes}
        artifacts = {r.id: r for r in package.artifacts}
        for row in self.views:
            key = (row.before_id, row.after_id)
            if set(row.source_ids) != set(key):
                raise ValueError("Uncited view sources")
            if abs(row.assessable_after_fraction + row.unassessed_after_fraction - 1) > 1e-6:
                raise ValueError("Invalid visible coverage")
            for ids, records in ((row.candidate_ids, candidates), (row.boundary_ids, boundaries)):
                expected = {i for i, r in records.items() if (r.before_id, r.after_id) == key}
                if len(ids) != len(expected) or set(ids) != expected:
                    raise ValueError("Incomplete view observation citations")
                if any(
                    i not in records or (records[i].before_id, records[i].after_id) != key
                    for i in ids
                ):
                    raise ValueError("Uncited view observation")
        for crop in self.detail_crops:
            if crop.candidate_id not in candidates:
                raise ValueError("Detail crop lacks a candidate")
            candidate = candidates[crop.candidate_id]
            if (crop.before_id, crop.after_id) != (candidate.before_id, candidate.after_id):
                raise ValueError("Detail crop differs from candidate pair")
            if any(i not in artifacts for i in crop.artifact_ids):
                raise ValueError("Detail crop has uncited artifacts")
            for artifact_id, kind, cited in zip(
                crop.artifact_ids,
                ("before_crop", "after_crop", "valid_overlap"),
                ({crop.before_id}, {crop.after_id}, {crop.before_id, crop.after_id}),
                strict=True,
            ):
                artifact = artifacts[artifact_id]
                if (
                    artifact.kind != kind
                    or set(artifact.source_ids) != cited
                    or (artifact.width, artifact.height) != (crop.width, crop.height)
                ):
                    raise ValueError("Detail crop artifact frame differs from manifest")
        for row in self.recapture_guidance:
            if not set(row.source_ids).issubset(sources):
                raise ValueError("Uncited recapture guidance")
        for observation in self.surface_observations:
            key = (observation.before_id, observation.after_id)
            if key not in pairs:
                raise ValueError("Surface observation has uncited pair")
            for artifact_id, kind, cited in zip(
                observation.artifact_ids,
                ("before_crop", "after_crop", "valid_overlap", "difference_map"),
                ({key[0]}, {key[1]}, set(key), set(key)),
                strict=True,
            ):
                artifact = artifacts.get(artifact_id)
                if (
                    artifact is None
                    or artifact.kind != kind
                    or set(artifact.source_ids) != cited
                    or (artifact.width, artifact.height) != (observation.width, observation.height)
                ):
                    raise ValueError("Surface observation artifact frame differs from manifest")
            for box in observation.appearance_regions:
                bounds = observation.after_box
                if (
                    box.x1 < bounds.x1
                    or box.y1 < bounds.y1
                    or box.x2 > bounds.x2
                    or box.y2 > bounds.y2
                ):
                    raise ValueError("Surface region is outside its assessed tile")
        return self


class InspectionFailure(Contract):
    schema_version: Literal["3.1"] = "3.1"
    engine_version: Literal["ep-v3.1-advisory"] = "ep-v3.1-advisory"
    outcome: Literal["failed"] = "failed"
    payment_action: Literal["none"] = "none"
    human_review_required: Literal[True] = True
    error_code: str = Field(pattern=r"^[a-z0-9_]{1,80}$")
    failure_category: Literal["internal_model_or_runtime_failure"] = (
        "internal_model_or_runtime_failure"
    )
