"""Standalone optional OpenRouter inspection; no application imports or mutations."""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ep_engine.vlm_eval.api import inspect
from ep_engine.vlm_eval.contracts import Benchmark, Limits, Reply
from ep_engine.vlm_eval.environment import load_environment
from ep_engine.vlm_eval.evidence import safe_path
from ep_engine.vlm_eval.fusion import CombinedReport, fuse
from ep_engine.vlm_eval.openrouter import OpenRouter
from ep_engine.vlm_eval.provider import EvaluationError
from ep_engine.vlm_eval.runner import run, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify", "inspect", "evaluate"))
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mode", choices=("cv_only", "vlm_only", "hybrid"), default="cv_only")
    parser.add_argument(
        "--model", help="Explicit audited free-model override; .env is never modified"
    )
    parser.add_argument("--consent-external-images", action="store_true")
    parser.add_argument("--check-model", action="store_true")
    parser.add_argument("--max-requests", type=int, default=0)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--max-images", type=int, default=8)
    parser.add_argument("--disable-reasoning", action="store_true")
    parser.add_argument("--run-seconds", type=float, default=300)
    args = parser.parse_args()
    configured, receipt = load_environment(args.env_file)
    limits = Limits.model_validate(
        dict(
            configured.model_dump(),
            model=args.model or configured.model,
            allow_external=args.consent_external_images,
            max_requests=args.max_requests,
            max_output_tokens=args.max_output_tokens,
            max_images=args.max_images,
            reasoning_enabled=False if args.disable_reasoning else configured.reasoning_enabled,
            run_seconds=args.run_seconds,
        )
    )
    if args.action == "verify":
        receipt.update(selected_model=limits.model, explicit_override=args.model is not None)
        if args.check_model and limits.provider == "openrouter":
            # Capability GET contains no images, evidence, or user prompts.
            try:
                metadata = OpenRouter(
                    limits.model_copy(update={"allow_external": True}),
                    os.environ.get("OPENROUTER_API_KEY", ""),
                ).check_model()
                receipt["model_capabilities"] = metadata
            except EvaluationError as exc:
                receipt.update(model_check=exc.code, http_status=getattr(exc, "http_status", None))
        print(json.dumps(receipt, indent=2))
        if args.output:
            destination = safe_path(args.output)
            destination.mkdir(parents=True, exist_ok=True, mode=0o700)
            write_json(destination / "environment-verification.json", receipt)
        return
    if not args.input or not args.output:
        parser.error("inspect/evaluate require --input and --output")
    source = safe_path(args.input)
    if source.stat().st_size > 2_000_000:
        raise ValueError("Input byte budget exceeded")
    if args.action == "inspect":
        report = inspect(
            json.loads(source.read_bytes()), args.output, mode=args.mode, limits=limits
        )
        print(json.dumps(dict(decision=report.decision, payment_action=report.payment_action)))
    else:
        manifest = Benchmark.model_validate_json(source.read_bytes())
        summary = run(manifest, limits, args.output)
        destination = safe_path(args.output)
        write_json(
            destination / "model-selection.json",
            dict(
                configured_model=configured.model,
                selected_model=limits.model,
                explicit_override=args.model is not None,
            ),
        )
        records = json.loads((destination / "results.json").read_bytes())
        for case in manifest.cases[: limits.max_cases]:
            from ep_engine.v31.contracts import InspectionReport
            from ep_engine.vlm_eval.evidence import checked_bytes

            cv = InspectionReport.model_validate_json(checked_bytes(case.cv_report, case.cv_sha256))
            for row in (r for r in records if r["case_id"] == case.case_id):
                mode = row["mode"]
                combined = fuse(
                    cv.inspection_id,
                    mode,
                    cv if mode != "vlm_only" else None,
                    row if mode != "cv_only" else None,
                )
                write_json(
                    destination / f"{case.case_id}-{mode}.json", combined.model_dump(mode="json")
                )
        print(json.dumps(summary, indent=2))
    for name, contract in (("reply", Reply), ("combined-report", CombinedReport)):
        write_json(safe_path(args.output) / f"{name}.schema.json", contract.model_json_schema())


if __name__ == "__main__":
    main()
