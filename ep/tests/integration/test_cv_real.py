import hashlib
import os
import sys
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image

from ep_engine.cv.contracts import CVConfig
from ep_engine.cv.models import NativeModels
from ep_engine.cv.pipeline import CVPipeline, InputImage
from ep_engine.schemas.models import Box


@pytest.mark.real_inference
@pytest.mark.parametrize("device", ["cuda", "cpu"])
def test_genuine_pretrained_connected_pipeline(tmp_path, device):
    if os.environ.get("EP_RUN_REAL_CV") != "1":
        pytest.skip("Explicit real-model run required: EP_RUN_REAL_CV=1")
    source = Path(sys.prefix) / "Lib/site-packages/ultralytics/assets/bus.jpg"
    with Image.open(source) as image:
        image = image.convert("RGB")
        image.thumbnail((512, 512))
        rgb = np.asarray(image)
    target = Box(x1=0.03, y1=0.20, x2=0.99, y2=0.72)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    inputs = [
        InputImage(uuid4(), stage, rgb.copy(), digest, target) for stage in ("before", "after")
    ]
    models = NativeModels(device)
    package = CVPipeline(CVConfig(device=device, max_side=512), models).run(
        uuid4(), inputs, tmp_path / "real-artifacts"
    )
    assert package.outcome == "comparable"
    assert package.pairs[0].inliers >= 12
    assert package.pairs[0].cosine_similarity > 0.99
    assert package.candidates == []
    assert all(row.status == "segmented" for row in package.segmentation)
    assert package.metrics["device"] == device
    assert set(package.metrics["model_weight_sha256"]) == {"segment", "embedding"}
    assert len(package.artifacts) >= 8
    assert models.model is None
