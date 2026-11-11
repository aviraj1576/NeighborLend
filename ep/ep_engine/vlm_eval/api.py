"""Standalone orchestration. Existing v31.inspect remains local and unchanged."""

import time
from pathlib import Path

from ep_engine.cv.worker import load_inputs
from ep_engine.v31.api import inspect as inspect_cv
from ep_engine.v31.contracts import InspectionRequest
from ep_engine.vlm_eval.contracts import Case, Limits
from ep_engine.vlm_eval.evidence import safe_path, sha, verified_case
from ep_engine.vlm_eval.fusion import fuse
from ep_engine.vlm_eval.runner import Budget, assess, canonical, exclusive, write_json


def inspect(payload, output_dir, *, mode="cv_only", limits=None, models=None, learned=None):
    """Run one private inspection. Caller supplies explicit limits.allow_external consent.

    In-process CV callers own their GPU serialization/deadline as before. For an
    isolated GPU worker use run_v31.py, then enrich its verified report with evaluate_vlm.py.
    """
    if mode not in {"cv_only", "vlm_only", "hybrid"}:
        raise ValueError("Unknown standalone inspection mode")
    request = InspectionRequest.model_validate(payload)
    limits = limits or Limits()
    output = safe_path(Path(output_dir))
    # Fresh outputs prevent accidentally reusing source-bound reports/artifacts.
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    with exclusive(output):
        manifest = output / "input.json"
        write_json(manifest, request.model_dump(mode="json"))
        report = None
        if mode != "vlm_only":
            report = inspect_cv(payload, output / "artifacts", models=models, learned=learned)
            write_json(output / "cv-result.json", report.model_dump(mode="json"))
        row = None
        if mode != "cv_only":
            (output / "cache").mkdir(mode=0o700)
            case = Case(
                case_id=str(request.inspection_id),
                input_manifest=manifest,
                input_sha256=sha(manifest.read_bytes()),
                cv_report=output / "cv-result.json",
                cv_sha256=sha((output / "cv-result.json").read_bytes()) if report else "0" * 64,
                object_group="standalone-unlabeled",
                kind="real_capture",
                provenance="Standalone inspection; independent labels not provided",
            )
            verified = (
                verified_case(case)
                if report
                else (
                    request,
                    None,
                    load_inputs(request.model_dump(mode="json"), preserve_original=True),
                    {},
                )
            )
            budget = Budget(
                output,
                limits,
                sha(
                    canonical(
                        dict(
                            input=case.input_sha256,
                            limits=limits.model_dump(),
                            mode=mode,
                        )
                    )
                ),
            )
            row = assess(
                mode, case, verified, limits, output, budget, time.monotonic() + limits.run_seconds
            )
            write_json(output / "vlm-result.json", row)
        combined = fuse(request.inspection_id, mode, report, row)
        write_json(output / "inspection.json", combined.model_dump(mode="json"))
        return combined
