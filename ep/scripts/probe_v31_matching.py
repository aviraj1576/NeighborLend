"""Bounded rotation experiment on frozen real masks; no labels or threshold tuning."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(1, str(Path(__file__).resolve().parents[1] / ".runtime/v3-packages"))

import cv2
import numpy as np
from PIL import Image

from ep_engine.core.exceptions import EPError
from ep_engine.cv.geometry import align_pair
from ep_engine.cv.worker import load_inputs
from ep_engine.v3.config import V3Config
from ep_engine.v3.matching import LoFTRMatcher, verify_correspondences

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / ".test-artifacts/ep-v31-20261111"


def main():
    jobs = json.loads((RELEASE / "evaluation-manifest.json").read_text("utf-8"))
    records = []
    for job in jobs:
        if job["kind"] != "real_pair" or job["category"] not in {"bag", "phone"}:
            continue
        payload = json.loads(Path(job["manifest"]).read_text("utf-8"))
        config = V3Config.model_validate(payload["config"])
        folder = RELEASE / "baseline-complete" / job["case_id"]
        package = json.loads((folder / "result.json").read_text("utf-8"))["cv_package"]
        inputs = load_inputs(payload)
        masks = []
        for row in package["segmentation"]:
            if row["mask_id"] is None:
                break
            with Image.open(folder / "artifacts" / f"{row['mask_id']}.png") as image:
                masks.append(np.asarray(image) > 0)
        if len(masks) != 2:
            records.append({"case_id": job["case_id"], "outcome": "surface_not_assessable"})
            continue
        matcher = LoFTRMatcher(config)
        before, after = [row.rgb for row in inputs]
        h, w = after.shape[:2]
        rotations = {
            0: np.eye(3),
            1: np.array([[0, 1, 0], [-1, 0, w - 1], [0, 0, 1.0]]),
            2: np.array([[-1, 0, w - 1], [0, -1, h - 1], [0, 0, 1.0]]),
            3: np.array([[0, -1, h - 1], [1, 0, 0], [0, 0, 1.0]]),
        }
        for turns, rotation in rotations.items():
            started = time.perf_counter()
            src, dst = matcher(
                before, np.rot90(after, turns).copy(), masks[0], np.rot90(masks[1], turns).copy()
            )
            if len(dst):
                dst = cv2.perspectiveTransform(dst[None], np.linalg.inv(rotation))[0]
            matrix, support, reason = verify_correspondences(src, dst, *masks, config)
            overlap = None
            if matrix is not None:
                try:
                    _, common = align_pair(before, *masks, matrix, config)
                    overlap = float(common.sum() / masks[1].sum())
                except EPError as error:
                    reason = error.code
            record = {
                "case_id": job["case_id"],
                "quarter_turns": turns,
                "matches": len(src),
                "support": support,
                "rejection": reason,
                "overlap": overlap,
                "seconds": time.perf_counter() - started,
            }
            records.append(record)
            print(record, flush=True)
        matcher.close()
    (RELEASE / "rotation-experiment.json").write_text(
        json.dumps(records, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
