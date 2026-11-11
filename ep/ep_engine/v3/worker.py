"""Separate v3 process entrypoint. Existing v1/v2 endpoints never call this worker."""

import json
import sys
from pathlib import Path
from uuid import UUID

from ep_engine.config import EP_ROOT
from ep_engine.core.exceptions import EPError
from ep_engine.cv.worker import load_inputs
from ep_engine.v3.config import V3Config
from ep_engine.v3.pipeline import V3Pipeline


def execute(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if (
        not source.is_relative_to(EP_ROOT)
        or source.stat().st_size > 1_000_000
        or not destination.is_relative_to(EP_ROOT)
        or destination == EP_ROOT
    ):
        raise ValueError("v3 requests and outputs must remain in dedicated EP directories")
    payload = json.loads(source.read_text("utf-8"))
    config = V3Config.model_validate(payload["config"])
    inputs = load_inputs(payload)
    result = V3Pipeline(config).run(
        UUID(payload["inspection_id"]), inputs, destination / "artifacts"
    )
    return {
        "engine_version": "ep-v3-experimental",
        "payment_action": "none",
        "human_review_required": True,
        "physical_identity_verified": False,
        "cv_package": result.model_dump(mode="json"),
    }


def main():
    target = Path(sys.argv[2]).resolve()
    try:
        result = execute(sys.argv[1], target)
        code = 0
    except Exception as exc:
        result = {
            "engine_version": "ep-v3-experimental",
            "payment_action": "none",
            "human_review_required": True,
            "outcome": "failed",
            "error_code": exc.code if isinstance(exc, EPError) else "worker_failure",
        }
        code = 3
    if not target.is_relative_to(EP_ROOT) or target == EP_ROOT:
        return 3
    (target / "result.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
