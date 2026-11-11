import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

EP_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    data_dir: Path = EP_ROOT / ".runtime"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=32 * 1024 * 1024)
    max_pixels: int = Field(default=16_000_000, ge=1, le=40_000_000)
    max_dimension: int = Field(default=8192, ge=1, le=16384)
    cors_origins: tuple[str, ...] = ()

    @field_validator("data_dir")
    @classmethod
    def local_data_only(cls, value: Path) -> Path:
        path = value if value.is_absolute() else EP_ROOT / value
        path = path.resolve()
        if not path.is_relative_to(EP_ROOT) or path == EP_ROOT:
            raise ValueError("EP data must be in a dedicated directory below ep/")
        return path

    @field_validator("cors_origins")
    @classmethod
    def explicit_origins(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if "*" in value:
            raise ValueError("Explicit CORS origins required")
        return value

    @classmethod
    def from_environment(cls):
        mapping = {
            "EP_DATA_DIR": "data_dir",
            "EP_MAX_UPLOAD_BYTES": "max_upload_bytes",
            "EP_MAX_PIXELS": "max_pixels",
            "EP_MAX_DIMENSION": "max_dimension",
        }
        values = {field: os.environ[key] for key, field in mapping.items() if key in os.environ}
        if os.environ.get("EP_CORS_ORIGINS"):
            values["cors_origins"] = json.loads(os.environ["EP_CORS_ORIGINS"])
        return cls(**values)
