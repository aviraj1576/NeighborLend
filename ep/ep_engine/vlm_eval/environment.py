"""Explicit backend-only configuration loading; never import application settings."""

import os
import re
from pathlib import Path

from ep_engine.vlm_eval.contracts import Limits

NAMES = {
    "OPENROUTER_API_KEY",
    "OPENROUTER_MODEL",
    "OPENROUTER_BASE_URL",
    "OPENROUTER_TIMEOUT_SECONDS",
    "EP_VLM_ENABLED",
    "EP_VLM_PROVIDER",
}


def load_environment(path=None):
    values = {}
    if path is not None:
        path = Path(path)
        if not path.is_file() or path.stat().st_size > 100_000:
            raise ValueError("Invalid explicit environment file")
        for line in path.read_text("utf-8-sig").splitlines():
            match = re.fullmatch(r"\s*(?:export\s+)?([A-Z_]+)\s*=\s*(.*?)\s*", line)
            if not match or match[1] not in NAMES:
                continue
            if match[1] in values:
                raise ValueError("Duplicate inspection environment setting")
            value = match[2]
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[match[1]] = value
    # Process configuration takes precedence. No unrelated .env settings are loaded.
    values.update({name: os.environ[name] for name in NAMES if name in os.environ})
    enabled = values.get("EP_VLM_ENABLED", "false").casefold()
    if enabled not in {"true", "false", "1", "0"}:
        raise ValueError("EP_VLM_ENABLED must be a boolean")
    active = enabled in {"true", "1"}
    provider = values.get("EP_VLM_PROVIDER", "disabled") if active else "disabled"
    if provider not in {"disabled", "openrouter"}:
        raise ValueError("Unsupported standalone environment provider")
    key = values.get("OPENROUTER_API_KEY", "")
    if key and not re.fullmatch(r"[!-~]{20,512}", key):
        raise ValueError("Invalid OpenRouter credential format")
    limits = Limits(
        provider=provider,
        model=values.get("OPENROUTER_MODEL", "unconfigured"),
        base_url=values.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        request_seconds=float(values.get("OPENROUTER_TIMEOUT_SECONDS", "25")),
        max_cost_usd=0,
        input_usd_per_million=0,
        output_usd_per_million=0,
        free_only=True,
    )
    if key:
        os.environ["OPENROUTER_API_KEY"] = key
    return limits, dict(
        enabled=active,
        provider=provider,
        model=limits.model,
        base_url=limits.base_url,
        timeout_seconds=limits.request_seconds,
        credential_present=bool(key),
    )
