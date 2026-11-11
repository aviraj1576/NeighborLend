from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictBool, model_validator

from ep_engine.v31.contracts import Contract

Mode = Literal["cv_only", "vlm_only", "hybrid"]
Unit = Annotated[float, Field(ge=0, le=1)]


class IndependentLabel(Contract):
    status: Literal["independently_reviewed"]
    task: Literal["visible_appearance_change"]
    change_present: StrictBool
    reviewer: str = Field(min_length=1, max_length=120)
    basis: str = Field(min_length=10, max_length=1200)
    annotation_version: str = Field(min_length=1, max_length=100)


class Case(Contract):
    case_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    input_manifest: Path
    input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    cv_report: Path
    cv_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    object_group: str = Field(min_length=1, max_length=120)
    split: Literal["development", "calibration", "test", "software_control"] = "development"
    provenance: str = Field(min_length=10, max_length=1200)
    kind: Literal["real_capture", "exact_repeat", "different_object", "synthetic"]
    label: IndependentLabel | None = None


class Benchmark(Contract):
    schema_version: Literal["1.0"] = "1.0"
    cases: list[Case] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_cases(self):
        if len({c.case_id for c in self.cases}) != len(self.cases):
            raise ValueError("Duplicate case IDs")
        groups = {}
        for case in self.cases:
            if case.object_group in groups and groups[case.object_group] != case.split:
                raise ValueError("Physical object/session group crosses splits")
            groups[case.object_group] = case.split
        return self


class Limits(Contract):
    provider: Literal["disabled", "gemini", "openrouter", "offline_fixture"] = "disabled"
    model: str = Field(default="unconfigured", pattern=r"^[A-Za-z0-9._:/-]{1,140}$")
    base_url: Literal["https://openrouter.ai/api/v1"] = "https://openrouter.ai/api/v1"
    metadata_retries: int = Field(default=1, ge=0, le=2)
    generation_retries: int = Field(default=0, ge=0, le=1)
    reasoning_enabled: bool | None = None
    min_request_interval_seconds: float = Field(default=3, ge=0, le=60)
    allow_external: bool = False
    free_only: bool = True
    free_tier_confirmed: bool = False
    max_cases: int = Field(default=56, ge=1, le=200)
    max_requests: int = Field(default=6, ge=0, le=400)
    run_seconds: float = Field(default=300, ge=1, le=3600)
    request_seconds: float = Field(default=25, ge=0.1, le=60)
    max_input_tokens: int = Field(default=20000, ge=100, le=100000)
    max_output_tokens: int = Field(default=2048, ge=128, le=4096)
    max_cost_usd: float = Field(default=0.25, ge=0, le=20)
    input_usd_per_million: float | None = Field(default=None, ge=0, le=10000)
    output_usd_per_million: float | None = Field(default=None, ge=0, le=10000)
    max_images: int = Field(default=8, ge=2, le=12)
    max_image_bytes: int = Field(default=8_000_000, ge=1000, le=16_000_000)


class Region(Contract):
    image_id: UUID
    box: tuple[Unit, Unit, Unit, Unit] = Field(
        description=(
            "[x_min,y_min,x_max,y_max], fractions in [0,1] of the original image; "
            "never 0..1000 or pixel coordinates"
        )
    )

    @model_validator(mode="after")
    def normalized(self):
        x1, y1, x2, y2 = self.box
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise ValueError("Region must be normalized to its cited image")
        return self


class Observation(Contract):
    before_id: UUID
    after_id: UUID
    before_region: Region
    after_region: Region
    before_visible: str = Field(min_length=1, max_length=400)
    after_visible: str = Field(min_length=1, max_length=400)
    explanation: str = Field(min_length=1, max_length=600)
    interpretation: Literal["appearance_only", "possible_damage_indicator"] = "appearance_only"
    alternatives: list[str] = Field(min_length=1, max_length=8)
    evidence_ids: list[UUID] = Field(min_length=2, max_length=12)


class Reply(Contract):
    change: Literal["visible_difference", "no_visible_difference", "uncertain"]
    observations: list[Observation] = Field(default_factory=list, max_length=8)
    uncertainty: list[str] = Field(min_length=1, max_length=12)
    recapture_guidance: list[str] = Field(default_factory=list, max_length=6)
    physical_identity_verified: Literal[False] = False
    payment_action: Literal["none"] = "none"
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def grounded(self):
        if (self.change == "visible_difference") != bool(self.observations):
            raise ValueError(
                "A positive requires grounded observations; others must abstain on regions"
            )
        return self
