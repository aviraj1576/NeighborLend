"""Private, provenance-aware v3/v3.1 evaluation; never infer labels from filenames."""

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ROOT / ".test-artifacts/updated-dataset-v3-20261110-01"
RELEASE = ROOT / ".test-artifacts/ep-v31-20261111"


def read(path):
    return json.loads(path.read_text("utf-8-sig"))


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", "utf-8")


def worker(manifest, revision, output):
    # The baseline imports the immutable source snapshot, using the SAME audited
    # assets, image derivatives and resource paths as the live standalone engine.
    sys.path.insert(0, str(RELEASE / "frozen" if revision == "baseline" else ROOT))
    # These optional packages were already installed into EP's local target;
    # they are intentionally absent from the shared Conda site-packages.
    sys.path.insert(1, str(ROOT / ".runtime/v3-packages"))
    import ep_engine.config as settings

    settings.EP_ROOT = ROOT
    import cv2
    import torch

    from ep_engine.cv.worker import load_inputs
    from ep_engine.v3.config import V3Config
    from ep_engine.v3.pipeline import V3Pipeline

    payload = read(manifest)
    cv2.setRNGSeed(0)
    torch.manual_seed(0)
    config = V3Config.model_validate(payload["config"])
    if revision == "current":
        from ep_engine.v31.api import inspect

        report = inspect(payload, output / "artifacts")
        result = report.model_dump(mode="json")
        package = result["cv_package"]
    else:
        package = (
            V3Pipeline(config)
            .run(UUID(payload["inspection_id"]), load_inputs(payload), output / "artifacts")
            .model_dump(mode="json")
        )
        result = {"cv_package": package, "payment_action": "none"}
    write(output / "result.json", result)
    write(
        output / "environment.json",
        {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "opencv": cv2.__version__,
            "gpu": torch.cuda.get_device_name(0),
            "seed": 0,
            "revision": revision,
            "imported_pipeline": str(sys.modules["ep_engine.v3.pipeline"].__file__),
            "source_sha256": {
                str(
                    path.relative_to(ROOT if revision == "current" else RELEASE / "frozen")
                ): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in Path(sys.modules["ep_engine"].__file__).parent.rglob("*.py")
            },
        },
    )


def jobs():
    records = read(HISTORICAL / "jobs.json")
    controls = RELEASE / "control-manifests"
    controls.mkdir(exist_ok=True)
    # Distinct categories give defensible different-object controls. There are no
    # independently reviewed same-category physical identity labels in this set.
    pairs = [row for row in records if row["kind"] == "real_pair"]
    front = {row["category"]: row for row in pairs if row["case_id"].endswith("front")}
    categories = sorted(front)
    for index, category in enumerate(categories):
        other = categories[(index + 1) % len(categories)]
        first, second = (
            read(Path(front[category]["manifest"])),
            read(Path(front[other]["manifest"])),
        )
        payload = {**first, "evidence": [first["evidence"][0], second["evidence"][1]]}
        path = controls / f"different-{category}-{other}.json"
        if not path.exists():
            write(path, payload)
        records.append(
            {
                "case_id": path.stem,
                "kind": "different_object_control",
                "category": f"{category}/{other}",
                "manifest": str(path),
                "physical_damage_label": None,
                "identity_label": "different_objects",
            }
        )
    # Separate earlier capture collection, retained as unlabeled regression data.
    # Several named before/after files are byte-identical: do NOT call these
    # independently captured unchanged controls or held-out physical objects.
    archive = ROOT / ".test-artifacts/rental-image-evaluation-20261110-01/private/cv/work"
    for source in sorted(archive.glob("*/input.json")):
        name = source.parent.name
        if name.count("-") != 1 or name.split("-")[0] not in {"bag", "clock", "phone", "speaker"}:
            continue
        payload = read(source)
        if len(payload["evidence"]) != 2:
            continue
        payload["config"] = read(HISTORICAL / "config.json")
        path = controls / f"archive-{name}.json"
        if not path.exists():
            write(path, payload)
        records.append(
            {
                "case_id": f"archive-{name}",
                "kind": "historical_unlabeled_pair",
                "category": name.split("-")[0],
                "manifest": str(path),
                "physical_damage_label": None,
                "pixel_duplicate": payload["evidence"][0]["normalized_sha256"]
                == payload["evidence"][1]["normalized_sha256"],
            }
        )
    for row in records:
        row["manifest_sha256"] = hashlib.sha256(Path(row["manifest"]).read_bytes()).hexdigest()
        row["partition"] = "engineering_regression_unlabeled"
    return records


def summarize(records):
    groups = defaultdict(list)
    for row in records:
        groups[row["kind"]].append(row)
    result = {
        "unit": "inspection job; real_pair jobs each contain one before/after pair",
        "physical_damage_metrics": None,
        "reason": "No independent damage labels",
        "payment_action": "none",
        "groups": {},
    }
    for kind, rows in groups.items():
        seconds = sorted(row["wall_seconds"] for row in rows)
        result["groups"][kind] = {
            "count": len(rows),
            "outcomes": dict(Counter(r["outcome"] for r in rows)),
            "proposal_jobs": sum(r.get("appearance_proposals", 0) > 0 for r in rows),
            "boundary_jobs": sum(r.get("boundary_hypotheses", 0) > 0 for r in rows),
            "confirmed_identity_jobs": sum(
                r.get("physical_identity_verified", False) for r in rows
            ),
            "median_wall_seconds": statistics.median(seconds),
            "peak_cuda_allocated_bytes": max(r.get("cuda_allocated", 0) for r in rows),
            "peak_cuda_reserved_bytes": max(r.get("cuda_reserved", 0) for r in rows),
            "peak_host_bytes": max(r.get("host_peak", 0) for r in rows),
            "categories": {
                category: dict(Counter(r["outcome"] for r in rows if r["category"] == category))
                for category in sorted({r["category"] for r in rows})
            },
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision", choices=("baseline", "current"))
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--campaign", default="complete")
    args = parser.parse_args()
    if args.worker:
        try:
            worker(args.worker, args.revision, args.output)
            return 0
        except Exception:
            # Preserve full diagnostics privately; expected pipeline failures and
            # programming errors remain distinguishable in the experiment ledger.
            (args.output / "traceback.txt").write_text(traceback.format_exc(), "utf-8")
            return 3
    destination = RELEASE / f"{args.revision}-{args.campaign}"
    destination.mkdir(exist_ok=True)
    manifest = jobs()
    write(RELEASE / "evaluation-manifest.json", manifest)
    records_path = destination / "executions.json"
    records = read(records_path) if records_path.exists() else []
    done = {row["case_id"] for row in records}
    count = 0
    for row in manifest:
        if row["case_id"] in done or args.limit is not None and count >= args.limit:
            continue
        output = destination / row["case_id"]
        output.mkdir(exist_ok=False)
        started = time.perf_counter()
        with (output / "worker.log").open("wb") as log:
            try:
                execution = subprocess.run(  # noqa: S603 - fixed local interpreter, no shell
                    [
                        sys.executable,
                        "-B",
                        str(Path(__file__).resolve()),
                        args.revision,
                        "--worker",
                        row["manifest"],
                        "--output",
                        str(output),
                    ],
                    cwd=ROOT,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                    timeout=240,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                code = execution.returncode
            except subprocess.TimeoutExpired:
                code = -1
        result = read(output / "result.json") if (output / "result.json").exists() else {}
        package = result.get("cv_package", {})
        metrics = result.get("runtime", package.get("metrics", {}))
        record = {
            **row,
            "exit_code": code,
            "wall_seconds": time.perf_counter() - started,
            "outcome": package.get("outcome", "failed"),
            "appearance_proposals": len(package.get("candidates", [])),
            "boundary_hypotheses": len(package.get("boundary_changes", [])),
            "physical_identity_verified": result.get("physical_identity_verified", False),
            "pipeline_seconds": metrics.get("total_seconds"),
            "cuda_allocated": metrics.get("peak_cuda_allocated_bytes", 0),
            "cuda_reserved": metrics.get("peak_cuda_reserved_bytes", 0),
            "host_peak": metrics.get("process_peak_working_set_bytes", 0),
        }
        records.append(record)
        write(records_path, records)
        write(destination / "summary.json", summarize(records))
        print(
            args.revision,
            row["case_id"],
            record["outcome"],
            round(record["wall_seconds"], 2),
            flush=True,
        )
        count += 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
