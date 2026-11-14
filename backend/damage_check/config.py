"""Module configuration. Everything comes from DAMAGE_* environment variables so
nothing here can collide with the host application's own settings."""
import os
from dataclasses import dataclass
from typing import Optional


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    provider: str = "gemini"                 # "gemini" or "mock"
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.5-flash"   # check the model id in AI Studio
    max_concurrency: int = 2                 # parallel view comparisons
    request_timeout: float = 60.0            # seconds per model call
    max_retries: int = 4                     # retries on 429 / 5xx
    max_upload_bytes: int = 8 * 1024 * 1024
    max_image_side: int = 1024               # downscale before sending to the model
    require_all_views: bool = True           # need all 6 before + 6 after photos

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            provider=os.environ.get("DAMAGE_PROVIDER", "gemini").lower(),
            gemini_api_key=os.environ.get("DAMAGE_GEMINI_API_KEY") or None,
            gemini_model=os.environ.get("DAMAGE_GEMINI_MODEL", "gemini-3.5-flash"),
            max_concurrency=max(1, _int("DAMAGE_MAX_CONCURRENCY", 2)),
            request_timeout=_float("DAMAGE_REQUEST_TIMEOUT", 60.0),
            max_retries=max(0, _int("DAMAGE_MAX_RETRIES", 4)),
            max_upload_bytes=_int("DAMAGE_MAX_UPLOAD_BYTES", 8 * 1024 * 1024),
            max_image_side=_int("DAMAGE_MAX_IMAGE_SIDE", 1024),
            require_all_views=_bool("DAMAGE_REQUIRE_ALL_VIEWS", True),
        )
