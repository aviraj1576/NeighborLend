"""Native object crops at two bounded LoFTR resolutions, verified in processing coordinates."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(1, str(Path(__file__).resolve().parents[1] / ".runtime/v3-packages"))

import cv2
import numpy as np
from PIL import Image

from ep_engine.cv.worker import load_inputs
from ep_engine.v3.config import V3Config
from ep_engine.v3.matching import LoFTRMatcher, verify_correspondences
from ep_engine.v31.coordinates import resize_frame
from ep_engine.v31.matching import cropped_matches

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / ".test-artifacts/ep-v31-20261111"
OUT = ROOT / ".test-artifacts/ep-v31-improvement-20261111"


def main():
    cv2.setNumThreads(1)
    records = []
    jobs = json.loads((OLD / "evaluation-manifest.json").read_text())
    for job in jobs:
        if (
            job["kind"] != "real_pair"
            or job["category"] not in {"bag", "shoes", "clock"}
            or job["case_id"]
            in {"shoes-back", "shoes-front", "shoes-side1", "clock-back", "clock-front"}
        ):
            continue
        payload = json.loads(Path(job["manifest"]).read_text())
        rows = load_inputs(payload, preserve_original=True)
        package = json.loads((OLD / f"current-release/{job['case_id']}/result.json").read_text())[
            "cv_package"
        ]
        masks = [
            np.asarray(
                Image.open(OLD / f"current-release/{job['case_id']}/artifacts/{seg['mask_id']}.png")
            )
            > 0
            for seg in package["segmentation"]
        ]
        native = [r.original_rgb for r in rows]
        native_masks = [
            cv2.warpPerspective(
                mask.astype(np.uint8),
                resize_frame(mask.shape, image.shape[:2]),
                (image.shape[1], image.shape[0]),
                flags=cv2.INTER_NEAREST,
            ).astype(bool)
            for image, mask in zip(native, masks, strict=True)
        ]
        for side in (512, 640):
            config = V3Config.model_validate(payload["config"]).model_copy(
                update={"learned_max_side": side}
            )
            matcher = LoFTRMatcher(config)
            for turn in range(4):
                start = time.perf_counter()
                src, dst = cropped_matches(matcher, *native, *native_masks, turn)
                points = []
                for p, row in zip((src, dst), rows, strict=True):
                    points.append(
                        cv2.perspectiveTransform(
                            p[None], resize_frame(row.original_rgb.shape[:2], row.rgb.shape[:2])
                        )[0]
                        if len(p)
                        else p
                    )
                cv2.setRNGSeed(0)
                matrix, support, reason = verify_correspondences(*points, *masks, config)
                record = dict(
                    case=job["case_id"],
                    side=side,
                    turn=turn,
                    matches=len(src),
                    support=support,
                    reason=reason,
                    seconds=time.perf_counter() - start,
                )
                records.append(record)
                print(json.dumps(record), flush=True)
            matcher.close()
    (OUT / "native-matching-experiment.json").write_text(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
