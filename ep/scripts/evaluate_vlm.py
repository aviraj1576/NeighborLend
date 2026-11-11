"""Prepare and run a bounded standalone CV/VLM/hybrid comparison. No Git or databases."""

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ep_engine.vlm_eval.contracts import Benchmark, Case, Limits, Reply
from ep_engine.vlm_eval.evidence import safe_path, sha
from ep_engine.vlm_eval.runner import run, write_json

ROOT = Path(__file__).resolve().parents[1]


def load_key_file(path):
    """Only the explicitly named key file; never execute dotenv content or echo keys."""
    path = path.resolve()
    if not path.is_file() or path.stat().st_size > 100_000:
        raise ValueError("Invalid credential file")
    matches = []
    for line in path.read_text("utf-8-sig").splitlines():
        match = re.fullmatch(r"\s*(?:export\s+)?GEMINI_API_KEY\s*=\s*(.*?)\s*", line)
        if match:
            value = match.group(1).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            # Treat credentials as opaque printable header values, not a guessed
            # vendor prefix/alphabet. CR/LF, whitespace and unbounded values fail.
            if not re.fullmatch(r"[!-~]{20,512}", value):
                raise ValueError("Invalid Gemini credential format")
            matches.append(value)
    if len(matches) != 1:
        raise ValueError("Configure exactly one GEMINI_API_KEY in the explicit key file")
    os.environ["GEMINI_API_KEY"] = matches[0]


def prepare_current(destination):
    old = ROOT / ".test-artifacts/ep-v31-20261111"
    records = json.loads((old / "evaluation-manifest.json").read_text("utf-8"))
    cases = []
    for record in records:
        request = safe_path(Path(record["manifest"]))
        report = safe_path(old / "current-refinement-final" / record["case_id"] / "result.json")
        kind = (
            "exact_repeat"
            if record["kind"] == "exact_repeat_control"
            else "different_object"
            if record["kind"] == "different_object_control"
            else "real_capture"
        )
        # The existing manifest explicitly supplies no independent condition labels.
        # Exact pixels and category controls are software safety controls, not damage truth.
        cases.append(
            Case(
                case_id=record["case_id"],
                input_manifest=request,
                input_sha256=sha(request.read_bytes()),
                cv_report=report,
                cv_sha256=sha(report.read_bytes()),
                object_group="existing-collection-no-physical-holdout",
                kind=kind,
                provenance=(
                    "Existing engineering capture collection; "
                    "physical identity and damage labels unverified"
                ),
            )
        )
    destination = safe_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_json(destination, Benchmark(cases=cases).model_dump(mode="json"))
    print(json.dumps(dict(cases=len(cases), independent_damage_labels=0)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    prepare = actions.add_parser("prepare-current")
    prepare.add_argument("output", type=Path)
    execute = actions.add_parser("run")
    execute.add_argument("manifest", type=Path)
    execute.add_argument("--config", type=Path, required=True)
    execute.add_argument("--output", type=Path, required=True)
    execute.add_argument(
        "--key-env", type=Path, help="Read only GEMINI_API_KEY from this explicit local file"
    )
    args = parser.parse_args()
    if args.action == "prepare-current":
        prepare_current(args.output)
        return
    manifest = safe_path(args.manifest)
    config = safe_path(args.config)
    if manifest.stat().st_size > 2_000_000 or config.stat().st_size > 100_000:
        raise ValueError("Manifest/config byte budget exceeded")
    benchmark = Benchmark.model_validate_json(manifest.read_bytes())
    limits = Limits.model_validate_json(config.read_bytes())
    if args.key_env:
        load_key_file(args.key_env)
    summary = run(benchmark, limits, args.output)
    for name, contract in (("benchmark", Benchmark), ("limits", Limits), ("reply", Reply)):
        write_json(safe_path(args.output) / f"{name}.schema.json", contract.model_json_schema())
    print(json.dumps(summary, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
