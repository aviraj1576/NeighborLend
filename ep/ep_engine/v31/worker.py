"""Isolated, offline v3.1 worker with private diagnostics and finite JSON output."""

import json
import sys
import traceback
from pathlib import Path

from ep_engine.config import EP_ROOT
from ep_engine.core.exceptions import EPError
from ep_engine.v31.api import inspect
from ep_engine.v31.contracts import InspectionFailure


def execute(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if (
        not source.is_relative_to(EP_ROOT)
        or source.stat().st_size > 1_000_000
        or not destination.is_relative_to(EP_ROOT)
        or destination == EP_ROOT
    ):
        raise ValueError("Use dedicated private EP request and output paths")
    report = inspect(json.loads(source.read_text("utf-8")), destination / "artifacts")
    return report.model_dump(mode="json")


def main():
    target = Path(sys.argv[2]).resolve()
    if not target.is_relative_to(EP_ROOT) or target == EP_ROOT:
        return 3
    try:
        result = execute(sys.argv[1], target)
        code = 0
    except Exception as exc:
        (target / "traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        result = InspectionFailure(
            error_code=exc.code if isinstance(exc, EPError) else "worker_failure"
        ).model_dump(mode="json")
        code = 3
    (target / "result.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
