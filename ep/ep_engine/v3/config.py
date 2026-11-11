from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from ep_engine.config import EP_ROOT
from ep_engine.cv.contracts import CVConfig


class V3Config(CVConfig):
    # Quality/calibration thresholds deliberately inherit the measured baseline.
    learned_matcher: Literal["disabled", "loftr"] = "disabled"
    compare_matchers: bool = False
    geometry_backend: Literal["opencv", "kornia"] = "opencv"
    alignment_backend: Literal["opencv", "cuda"] = "opencv"
    appearance_backend: Literal["opencv", "cuda"] = "cuda"
    learned_max_side: int = Field(default=512, ge=128, le=640)
    learned_confidence: float = Field(default=0.5, ge=0, le=1)
    checkpoint: Path | None = None
    checkpoint_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    embedding_cache_entries: int = Field(default=32, ge=0, le=128)

    @model_validator(mode="after")
    def local_checkpoint(self):
        if self.learned_matcher != "disabled":
            if self.checkpoint is None or self.checkpoint_sha256 is None:
                raise ValueError("LoFTR requires a local checkpoint and SHA-256; no auto-download")
            root = (EP_ROOT / ".runtime" / "v3-models").resolve()
            path = self.checkpoint.resolve()
            if (
                not root.is_relative_to(EP_ROOT)
                or self.checkpoint.is_symlink()
                or not path.is_relative_to(root)
            ):
                raise ValueError("Optional checkpoints must remain below ep/.runtime/v3-models")
        return self
