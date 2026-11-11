import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ep_engine.cv.numerics import finite_tree
from ep_engine.schemas.models import Box


class CVContract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: Literal["2.0"] = "2.0"


class CVConfig(CVContract):
    threshold_version: str = "cv-thresholds-2.0-experimental"
    device: Literal["cuda", "cpu", "auto"] = "cuda"
    max_side: int = Field(default=768, ge=128, le=1024)
    max_images: int = Field(default=8, ge=2, le=12)
    max_pairs: int = Field(default=16, ge=1, le=36)
    timeout_seconds: float = Field(default=180, ge=1, le=900)
    min_side: int = Field(default=128, ge=16, le=512)
    min_focus: float = Field(default=25, ge=0, le=1000)
    min_contrast: float = Field(default=10, ge=0, le=100)
    max_clipped_fraction: float = Field(default=0.65, gt=0, lt=1)
    min_similarity: float = Field(default=0.65, ge=-1, le=1)
    min_inliers: int = Field(default=12, ge=8, le=200)
    min_inlier_ratio: float = Field(default=0.45, gt=0, le=1)
    min_overlap: float = Field(default=0.35, gt=0, le=1)
    difference_threshold: float = Field(default=0.15, gt=0, lt=1)
    min_candidate_area: int = Field(default=16, ge=4, le=10000)


class RunRequest(CVContract):
    targets: dict[UUID, Box] = Field(default_factory=dict, max_length=12)
    config: CVConfig = Field(default_factory=CVConfig)


class Quality(CVContract):
    evidence_id: UUID
    status: Literal["usable", "needs_recapture", "inconclusive"]
    width: int
    height: int
    focus_variance: float
    contrast_std: float
    mean_exposure: float
    dark_fraction: float
    bright_fraction: float
    object_fraction: float | None = None
    touches_frame: bool = False
    reasons: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class Artifact(CVContract):
    id: UUID
    source_ids: list[UUID] = Field(min_length=1)
    kind: Literal[
        "object_mask",
        "object_crop",
        "feature_matches",
        "valid_overlap",
        "difference_map",
        "candidate_overlay",
        "before_crop",
        "after_crop",
        "aligned_before",
        "alignment_overlay",
        "boundary_change_map",
        "boundary_overlay",
    ]
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_size: int = Field(gt=0, le=20_000_000)
    width: int = Field(gt=0, le=2048)
    height: int = Field(gt=0, le=2048)
    content_type: Literal["image/png"] = "image/png"


class Segmentation(CVContract):
    evidence_id: UUID
    status: Literal["segmented", "inconclusive"]
    box: Box | None = None
    area_fraction: float | None = Field(default=None, ge=0, le=1)
    mask_id: UUID | None = None
    limitations: list[str] = Field(default_factory=list)
    target_support: dict[str, float] = Field(default_factory=dict)


class BoundaryChange(CVContract):
    id: UUID
    before_id: UUID
    after_id: UUID
    before_box: Box
    after_box: Box
    direction: Literal["potentially_missing", "additional_or_displaced"]
    observation: Literal["object_boundary_change"] = "object_boundary_change"
    area_pixels: int = Field(gt=0)
    artifact_ids: list[UUID] = Field(min_length=1)
    limitations: list[str] = Field(
        default_factory=lambda: [
            "Occlusion, pose and segmentation error can resemble a missing component",
            "No semantic part identity or physical loss is confirmed; human review required",
        ]
    )


class Candidate(CVContract):
    id: UUID
    before_id: UUID
    after_id: UUID
    before_box: Box
    after_box: Box
    observation: Literal["local_appearance_change"] = "local_appearance_change"
    method: str = "masked_gaussian_ssim_and_absolute_difference_v1"
    area_pixels: int = Field(gt=0)
    mean_difference: float = Field(ge=0, le=1)
    inlier_ratio: float = Field(ge=0, le=1)
    artifact_ids: list[UUID] = Field(default_factory=list)
    limitations: list[str] = Field(
        default_factory=lambda: ["Visual change is not confirmed physical damage"]
    )


class Pair(CVContract):
    before_id: UUID
    after_id: UUID
    status: Literal["comparable", "inconclusive"] = "inconclusive"
    identity: Literal["consistent_visual_evidence", "uncertain"] = "uncertain"
    method: str = "dinov2_s14_sift_mutual_ratio_ransac"
    cosine_similarity: float = Field(ge=-1, le=1)
    matches: int = Field(default=0, ge=0)
    local_matching_evaluated: bool = False
    alignment_status: Literal["not_attempted", "rejected", "aligned"] = "not_attempted"
    overlap_id: UUID | None = None
    inliers: int = Field(default=0, ge=0)
    inlier_ratio: float = Field(default=0, ge=0, le=1)
    median_reprojection_error: float | None = None
    overlap_fraction: float = Field(default=0, ge=0, le=1)
    homography: list[list[float]] | None = None
    reasons: list[str] = Field(default_factory=list)
    geometry_model: Literal["homography", "similarity"] = "homography"
    source_coverage: float = Field(default=0, ge=0, le=1)
    target_coverage: float = Field(default=0, ge=0, le=1)
    symmetric_reprojection_error: float | None = Field(default=None, ge=0)


class CVPackage(CVContract):
    inspection_id: UUID
    pipeline_version: Literal["ep-cv-2.0"] = "ep-cv-2.0"
    outcome: Literal["comparable", "partially_comparable", "inconclusive", "failed"]
    source_ids: list[UUID] = Field(min_length=2, max_length=12)
    source_hashes: dict[UUID, str]
    source_dimensions: dict[UUID, tuple[int, int]] = Field(default_factory=dict)
    processing_dimensions: dict[UUID, tuple[int, int]] = Field(default_factory=dict)
    coordinate_system: Literal["normalized_orientation_corrected_source"] = (
        "normalized_orientation_corrected_source"
    )
    quality: list[Quality]
    segmentation: list[Segmentation]
    pairs: list[Pair]
    candidates: list[Candidate] = Field(default_factory=list)
    boundary_changes: list[BoundaryChange] = Field(default_factory=list, max_length=120)
    artifacts: list[Artifact] = Field(default_factory=list, max_length=150)
    unmatched_ids: list[UUID] = Field(default_factory=list)
    models: dict[str, str]
    thresholds: CVConfig
    metrics: dict[str, float | int | str | dict] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def citations(self):
        finite_tree(self.metrics)
        allowed = set(self.source_ids)
        if len(allowed) != len(self.source_ids) or set(self.source_hashes) != allowed:
            raise ValueError("Invalid source manifest")
        if any(not re.fullmatch(r"[a-f0-9]{64}", digest) for digest in self.source_hashes.values()):
            raise ValueError("Invalid source digest")
        for dimensions in (self.source_dimensions, self.processing_dimensions):
            if set(dimensions) != allowed or any(min(size) < 1 for size in dimensions.values()):
                raise ValueError("Invalid source coordinate manifest")
        for key, (width, height) in self.processing_dimensions.items():
            source_width, source_height = self.source_dimensions[key]
            if (
                width > source_width
                or height > source_height
                or max(width, height) > self.thresholds.max_side
                or abs(width * source_height - height * source_width)
                > max(source_width, source_height)
            ):
                raise ValueError("Invalid processing coordinate scale")
        if {row.evidence_id for row in self.quality} != allowed or len(self.quality) != len(
            allowed
        ):
            raise ValueError("Quality coverage must include every source exactly once")
        if {row.evidence_id for row in self.segmentation} != allowed or len(
            self.segmentation
        ) != len(allowed):
            raise ValueError("Segmentation coverage must include every source exactly once")
        for row in self.quality + self.segmentation:
            if row.evidence_id not in allowed:
                raise ValueError("Uncited stage evidence")
        if any(
            (row.width, row.height) != self.processing_dimensions[row.evidence_id]
            for row in self.quality
        ):
            raise ValueError("Quality dimensions differ from the processing frame")
        if not set(self.unmatched_ids).issubset(allowed):
            raise ValueError("Uncited unmatched evidence")
        artifact_ids = {item.id for item in self.artifacts}
        if len(artifact_ids) != len(self.artifacts):
            raise ValueError("Duplicate artifacts")
        for artifact in self.artifacts:
            if not set(artifact.source_ids).issubset(allowed):
                raise ValueError("Uncited artifact source")
        for row in self.pairs + self.candidates + self.boundary_changes:
            if (
                row.before_id not in allowed
                or row.after_id not in allowed
                or row.before_id == row.after_id
            ):
                raise ValueError("Uncited pair")
        comparable_pairs = {
            (row.before_id, row.after_id) for row in self.pairs if row.status == "comparable"
        }
        if len({row.id for row in self.candidates}) != len(self.candidates):
            raise ValueError("Duplicate candidate IDs")
        if len({(row.before_id, row.after_id) for row in self.pairs}) != len(self.pairs):
            raise ValueError("Duplicate pair records")
        for row in self.candidates:
            if not set(row.artifact_ids).issubset(artifact_ids):
                raise ValueError("Missing candidate artifact")
            if (row.before_id, row.after_id) not in comparable_pairs:
                raise ValueError("Candidate has no comparable supporting pair")
        if len({r.id for r in self.boundary_changes}) != len(self.boundary_changes):
            raise ValueError("Duplicate boundary change IDs")
        for row in self.boundary_changes:
            if (row.before_id, row.after_id) not in comparable_pairs:
                raise ValueError("Boundary change lacks a comparable pair")
            if not set(row.artifact_ids).issubset(artifact_ids):
                raise ValueError("Missing boundary change artifacts")
            cited = [a for a in self.artifacts if a.id in row.artifact_ids]
            if not {"boundary_overlay", "boundary_change_map"}.issubset(
                {a.kind for a in cited}
            ) or any(set(a.source_ids) != {row.before_id, row.after_id} for a in cited):
                raise ValueError("Boundary change requires pair-specific boundary artifacts")
        artifacts = {row.id: row for row in self.artifacts}
        for row in self.segmentation:
            if row.status == "segmented" and (
                row.box is None
                or row.area_fraction is None
                or row.mask_id not in artifacts
                or artifacts[row.mask_id].kind != "object_mask"
                or row.evidence_id not in artifacts[row.mask_id].source_ids
            ):
                raise ValueError("Segmentation lacks a cited object mask")
        supported = {
            key
            for row in self.pairs
            if row.status == "comparable"
            for key in (row.before_id, row.after_id)
        }
        expected_unmatched = allowed - supported
        if set(self.unmatched_ids) != expected_unmatched:
            raise ValueError("Incorrect unmatched-view manifest")
        expected_outcome = (
            "inconclusive"
            if not supported
            else "partially_comparable"
            if expected_unmatched
            else "comparable"
        )
        if self.outcome != "failed" and self.outcome != expected_outcome:
            raise ValueError("Outcome does not reflect supported comparisons")
        return self
