"""Cold-model versus warm-cache inspections in separate frozen/current processes."""

import argparse
import json
import sys
import time
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".test-artifacts/ep-v31-20261111"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision", choices=("baseline", "current"))
    args = parser.parse_args()
    sys.path.insert(0, str(OUT / "frozen" if args.revision == "baseline" else ROOT))
    sys.path.insert(1, str(ROOT / ".runtime/v3-packages"))
    import ep_engine.config as settings

    settings.EP_ROOT = ROOT
    import cv2
    import torch

    from ep_engine.cv.worker import load_inputs
    from ep_engine.v3.config import V3Config
    from ep_engine.v3.pipeline import CachedModels, V3Pipeline

    source = ROOT / ".test-artifacts/updated-dataset-v3-20261110-01/jobs/speaker-back/input.json"
    payload = json.loads(source.read_text("utf-8"))
    config = V3Config.model_validate(payload["config"])
    destination = OUT / f"lifecycle-{args.revision}"
    destination.mkdir(exist_ok=False)
    rows = load_inputs(payload)
    models = CachedModels(config)
    records = []
    for index in range(3):
        cv2.setRNGSeed(0)
        torch.manual_seed(0)
        torch.cuda.synchronize()
        started = time.perf_counter()
        if args.revision == "baseline":
            package = V3Pipeline(config, models).run(
                UUID(payload["inspection_id"]), rows, destination / str(index) / "artifacts"
            )
        else:
            from ep_engine.v31.api import inspect_inputs

            package = inspect_inputs(
                UUID(payload["inspection_id"]),
                rows,
                destination / str(index) / "artifacts",
                config,
                models=models,
                high_resolution_crops=0,
            ).cv_package
        torch.cuda.synchronize()
        records.append(
            {
                "index": index,
                "kind": "cold_models" if index == 0 else "warm_embedding_cache",
                "seconds": time.perf_counter() - started,
                "outcome": package.outcome,
                "metrics": models.metrics(),
            }
        )
        print(args.revision, records[-1]["kind"], records[-1]["seconds"], flush=True)
    models.close()
    (destination / "summary.json").write_text(
        json.dumps(
            {
                "case": "speaker-back",
                "revision": args.revision,
                "records": records,
                "scope": (
                    "Same in-memory pixels; imports/decoder excluded; "
                    "original-detail crops disabled equally"
                ),
                "policy": (
                    "Models released per inspection; bounded CPU embedding LRU "
                    "persists across calls"
                ),
            },
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
