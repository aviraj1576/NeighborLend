import hashlib
import json
import os
from uuid import uuid4

import numpy as np
import pytest

from ep_engine.assessment.contracts import AssessmentOptions
from ep_engine.assessment.engine import assess
from ep_engine.assessment.providers import MockProvider
from ep_engine.cv.contracts import CVConfig
from ep_engine.cv.models import NativeModels
from ep_engine.cv.pipeline import CVPipeline, InputImage
from ep_engine.schemas.models import Box


@pytest.mark.real_inference
@pytest.mark.controlled_inference
@pytest.mark.parametrize("device", ["cuda", "cpu"])
def test_pretrained_synthetic_pipeline_and_gated_assessment(tmp_path, device):
    if os.environ.get("EP_RUN_CONTROLLED_CV") != "1":
        pytest.skip("Explicit controlled native execution required")
    rgb = np.full((256, 256, 3), 230, np.uint8)
    rgb[48:208, 48:208] = np.random.default_rng(42).integers(30, 170, (160, 160, 3), np.uint8)
    target = Box(x1=0.16, y1=0.16, x2=0.84, y2=0.84)
    after = rgb.copy()
    if device == "cuda":
        after[105:135, 110:140] = 0
    inputs = [
        InputImage(uuid4(), stage, image, hashlib.sha256(image.tobytes()).hexdigest(), target)
        for stage, image in (("before", rgb), ("after", after))
    ]
    package = CVPipeline(CVConfig(device=device, max_side=256), NativeModels(device)).run(
        uuid4(), inputs, tmp_path / "output"
    )
    assert package.outcome == "comparable"
    assert package.pairs[0].alignment_status == "aligned"
    assert package.metrics["device"] == device
    provider = MockProvider()
    report = assess(
        uuid4(),
        package,
        lambda key: (tmp_path / "output" / f"{key}.png").read_bytes(),
        AssessmentOptions(),
        provider,
    )
    if device == "cuda":
        assert package.candidates and report.mocked
        assert report.status == "inconclusive" and provider.calls == 1
        assert report.stage_statuses == [
            "damage_verification",
            "evidence_fusion",
            "report_generation",
        ]
    else:
        assert (
            not package.candidates and report.status == "no_visible_change" and provider.calls == 0
        )
    destination = tmp_path.parents[1] / f"phase34-{device}-controlled.json"
    destination.write_text(
        json.dumps(
            {
                "device": device,
                "cv_metrics": package.metrics,
                "assessment": report.model_dump(mode="json"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
