"""Genuine pretrained CUDA/CPU forwards on a locally installed sample; no image download."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PIL import Image

from ep_engine.cv.models import NativeModels


def main():
    root = Path(__file__).resolve().parents[1]
    sample = Path(sys.prefix) / "Lib/site-packages/ultralytics/assets/bus.jpg"
    image = Image.open(sample).convert("RGB")
    image.thumbnail((768, 768))
    rgb = np.asarray(image)
    records = []
    for device in ("cuda", "cpu"):
        models = NativeModels(device)
        try:
            started = time.perf_counter()
            mask = models.segment(rgb, (0.03, 0.20, 0.99, 0.72))
            segmentation_seconds = time.perf_counter() - started
            started = time.perf_counter()
            vector = models.embedding(rgb, mask)
            records.append(
                {
                    **models.metrics(),
                    "segmentation_seconds": segmentation_seconds,
                    "embedding_seconds": time.perf_counter() - started,
                    "mask_shape": list(mask.shape),
                    "mask_area_fraction": float(mask.mean()),
                    "embedding_shape": list(vector.shape),
                    "embedding_norm": float(np.linalg.norm(vector)),
                    "finite": bool(np.isfinite(vector).all()),
                    "sample_origin": str(sample),
                    "sample_note": (
                        "Existing bundled Ultralytics sample; no damage/identity ground truth"
                    ),
                }
            )
            print(json.dumps(records[-1]), flush=True)
        finally:
            models.close()
    target = root / ".test-artifacts/phase2-native-probe.json"
    target.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
