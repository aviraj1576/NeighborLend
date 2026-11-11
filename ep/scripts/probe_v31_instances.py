"""Inspect genuine touching-instance mask ambiguity without changing source evidence."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(1, str(Path(__file__).resolve().parents[1] / ".runtime/v3-packages"))

import cv2
import numpy as np
from PIL import Image

from ep_engine.cv.geometry import local_features
from ep_engine.cv.worker import load_inputs
from ep_engine.v3.config import V3Config
from ep_engine.v3.matching import HybridMatcher, verify_correspondences

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".test-artifacts/ep-v31-20261111"


def main():
    folder = OUT / "baseline-complete/shoes-back"
    package = json.loads((folder / "result.json").read_text("utf-8"))["cv_package"]
    payload = json.loads(
        (
            ROOT / ".test-artifacts/updated-dataset-v3-20261110-01/jobs/shoes-back/input.json"
        ).read_text("utf-8")
    )
    images = [row.rgb for row in load_inputs(payload)]
    masks = []
    morphology = []
    for row in package["segmentation"]:
        with Image.open(folder / "artifacts" / f"{row['mask_id']}.png") as image:
            mask = np.asarray(image) > 0
        masks.append(mask)
        morphology.append(
            {
                "evidence_id": row["evidence_id"],
                "original_area": int(mask.sum()),
                "eroded_component_areas": {
                    str(size): cv2.connectedComponentsWithStats(
                        cv2.erode(mask.astype(np.uint8), np.ones((size, size), np.uint8))
                    )[2][1:, cv2.CC_STAT_AREA].tolist()
                    for size in (5, 9, 17, 33, 49)
                },
            }
        )
    config = V3Config.model_validate(payload["config"])
    matcher = HybridMatcher(config)
    features = tuple(local_features(image, mask) for image, mask in zip(images, masks, strict=True))
    pair, matrix = matcher(
        *(row.id for row in load_inputs(payload)),
        *images,
        *masks,
        package["pairs"][0]["cosine_similarity"],
        config,
        features,
    )
    src, dst = next(iter(matcher.correspondences.values()))
    residual = np.linalg.norm(cv2.perspectiveTransform(src[None], matrix)[0] - dst, axis=1)
    outliers = residual > 3
    alternative, support, reason = verify_correspondences(
        src[outliers], dst[outliers], *masks, config
    )
    result = {
        "morphology": morphology,
        "matches": len(src),
        "outliers": int(outliers.sum()),
        "secondary_support": support,
        "secondary_rejection": reason,
        "secondary_matrix": alternative.tolist() if alternative is not None else None,
        "primary_pair": pair.model_dump(mode="json"),
    }
    matcher.close()
    (OUT / "instance-experiment.json").write_text(json.dumps(result, indent=2) + "\n", "utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
