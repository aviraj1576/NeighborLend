from collections.abc import Callable
from typing import Literal, Protocol
from uuid import UUID

from pydantic import Field

from ep_engine.schemas.models import Contract, Finding

StageName = Literal[
    "image_quality",
    "object_segmentation",
    "visual_features",
    "viewpoint_matching",
    "image_alignment",
    "change_candidates",
    "damage_verification",
    "evidence_fusion",
    "report_generation",
]
STAGE_ORDER: tuple[StageName, ...] = (
    "image_quality",
    "object_segmentation",
    "visual_features",
    "viewpoint_matching",
    "image_alignment",
    "change_candidates",
    "damage_verification",
    "evidence_fusion",
    "report_generation",
)


class StageResult(Contract):
    """All artifacts reference private adapter keys, never public URLs or file paths.

    Implementations must document their artifact encoding/version separately. Observations
    are evidence-backed statements, not a model confidence interpreted as probability.
    """

    stage: StageName
    evidence_ids: list[UUID] = Field(min_length=1)
    artifact_keys: list[UUID] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    abstain: bool = False


class PipelineContext(Contract):
    inspection_id: UUID
    reference_ids: list[UUID] = Field(min_length=1)
    return_ids: list[UUID] = Field(min_length=1)
    results: list[StageResult] = Field(default_factory=list)


StageImplementation = Callable[[PipelineContext], StageResult]


class ImageQualityAnalyzer(Protocol):
    """Decode/quality limitations; abstain when evidence cannot be assessed."""

    def __call__(self, context: PipelineContext) -> StageResult: ...


class ObjectSegmenter(Protocol):
    """Versioned masks bound to orientation-corrected evidence dimensions."""

    def __call__(self, context: PipelineContext) -> StageResult: ...


class VisualFeatureExtractor(Protocol):
    """Versioned pretrained embeddings; similarity alone does not establish identity."""

    def __call__(self, context: PipelineContext) -> StageResult: ...


class ViewpointMatcher(Protocol):
    """Comparable view pairs plus identity uncertainty and unmatched views."""

    def __call__(self, context: PipelineContext) -> StageResult: ...


class ImageAligner(Protocol):
    """Geometric transforms/inlier diagnostics with explicit alignment failures."""

    def __call__(self, context: PipelineContext) -> StageResult: ...


class ChangeCandidateDetector(Protocol):
    """Localized change candidates; differences are not automatically damage."""

    def __call__(self, context: PipelineContext) -> StageResult: ...


class DamageVerifier(Protocol):
    """Candidate verification with supporting/contradicting evidence; optional paid adapter."""

    def __call__(self, context: PipelineContext) -> StageResult: ...


class EvidenceFusionEngine(Protocol):
    """Resolve disagreements; inaccessible reference regions require abstention."""

    def __call__(self, context: PipelineContext) -> StageResult: ...


class InspectionReportGenerator(Protocol):
    """Evidence-cited findings with limitations and mandatory human review."""

    def __call__(self, context: PipelineContext) -> StageResult: ...
