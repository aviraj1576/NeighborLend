"""Measure FP32 four-view batching against the existing sequential DINO forwards."""

import json
import sys
import time
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import torch
from PIL import Image

from ep_engine.cv.models import NativeModels, check_embedding
from ep_engine.cv.targeting import embedding_canvas
from ep_engine.cv.worker import load_inputs

ROOT = Path(__file__).resolve().parents[1]


def main():
    old = ROOT / ".test-artifacts/ep-v31-20261111"
    out = ROOT / ".test-artifacts/ep-v31-improvement-20261111"
    model = NativeModels("cuda")
    network = model._load("embedding")
    records = []
    for name in ("bag-front", "phone-front", "speaker-side"):
        payload = json.loads(
            (
                ROOT / f".test-artifacts/updated-dataset-v3-20261110-01/jobs/{name}/input.json"
            ).read_text()
        )
        rows = load_inputs(payload)
        package = json.loads((old / f"current-release/{name}/result.json").read_text())[
            "cv_package"
        ]
        for row, seg in zip(rows, package["segmentation"], strict=True):
            mask = (
                np.asarray(
                    Image.open(old / f"current-release/{name}/artifacts/{seg['mask_id']}.png")
                )
                > 0
            )
            array = embedding_canvas(row.rgb, mask)
            array = (array - np.array([0.485, 0.456, 0.406], np.float32)) / np.array(
                [0.229, 0.224, 0.225], np.float32
            )
            batch = torch.from_numpy(
                np.stack([np.rot90(array, r).copy().transpose(2, 0, 1) for r in range(4)])
            ).to("cuda")
            values, times, peaks = {}, {}, {}
            for mode in ("sequential", "batch"):
                elapsed = []
                torch.cuda.reset_peak_memory_stats()
                for repetition in range(8):
                    torch.cuda.synchronize()
                    start = time.perf_counter()
                    with torch.inference_mode():
                        outputs = (
                            torch.cat([network(t[None]) for t in batch])
                            if mode == "sequential"
                            else network(batch)
                        )
                    raw = outputs.cpu().numpy()
                    values[mode] = check_embedding(
                        np.mean([check_embedding(v) for v in raw], axis=0)
                    )
                    torch.cuda.synchronize()
                    if repetition:
                        elapsed.append(time.perf_counter() - start)
                times[mode] = median(elapsed)
                peaks[mode] = torch.cuda.max_memory_allocated()
            record = dict(
                case=name,
                stage=row.stage,
                seconds=times,
                peak_bytes=peaks,
                max_embedding_error=float(np.max(np.abs(values["sequential"] - values["batch"]))),
                cosine=float(values["sequential"] @ values["batch"]),
            )
            records.append(record)
            print(json.dumps(record), flush=True)
    model.close()
    (out / "embedding-benchmark.json").write_text(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
