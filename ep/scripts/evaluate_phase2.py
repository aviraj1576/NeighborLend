"""Validate a private benchmark and optionally score independently reviewed labels."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ep_engine.config import EP_ROOT
from ep_engine.cv.evaluation import evaluate_cases, validate_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = validate_manifest(args.manifest)
    predictions = []
    if args.predictions:
        path = args.predictions.resolve()
        if not path.is_relative_to(EP_ROOT):
            raise ValueError("Predictions must remain inside EP")
        predictions = json.loads(path.read_text("utf-8"))["predictions"]
    report = evaluate_cases(cases, predictions, args.manifest.resolve().parent)
    report["scenario_counts"] = {
        tag: sum(tag in case.get("scenario_tags", []) for case in cases)
        for tag in sorted({tag for case in cases for tag in case.get("scenario_tags", [])})
    }
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        target = args.output.resolve()
        if not target.is_relative_to(EP_ROOT):
            raise ValueError("Evaluation reports must remain inside EP")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
