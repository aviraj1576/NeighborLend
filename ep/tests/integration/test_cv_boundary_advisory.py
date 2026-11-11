"""Boundary evidence, view constraints and advisory-only recovery contracts."""

from uuid import uuid4

import numpy as np
import pytest
from pydantic import ValidationError

from ep_engine.assessment.contracts import AssessmentOptions
from ep_engine.assessment.engine import assess
from ep_engine.assessment.providers import MockProvider
from ep_engine.cv.contracts import CVConfig, CVPackage
from ep_engine.cv.pipeline import CVPipeline, InputImage
from ep_engine.schemas.models import Box


class ShapeModels:
    """Generated scene contract adapter; not a pretrained model or accuracy result."""

    def __init__(self, fail_first=False):
        self.fail_first = fail_first
        self.closed = 0

    def segment(self, rgb, box):
        if self.fail_first:
            self.fail_first = False
            return np.ones(rgb.shape[:2], bool)
        return rgb[:, :, 0] < 200

    def embedding(self, rgb, mask):
        return np.ones(384, np.float32)

    def metrics(self):
        return {"device": "generated-shape-test-adapter"}

    def close(self):
        self.closed += 1


def scene():
    before = np.full((256, 256, 3), 230, np.uint8)
    before[40:215, 40:185] = np.random.default_rng(5).integers(30, 170, (175, 145, 3), np.uint8)
    before[90:145, 185:230] = np.random.default_rng(7).integers(30, 170, (55, 45, 3), np.uint8)
    after = before.copy()
    after[90:145, 185:230] = 230
    box = Box(x1=0.12, y1=0.12, x2=0.94, y2=0.9)
    return [
        InputImage(uuid4(), stage, image, digest * 64, box)
        for stage, image, digest in (("before", before, "a"), ("after", after, "b"))
    ]


def test_missing_component_hypothesis_cannot_be_reported_as_unchanged(tmp_path):
    package = CVPipeline(CVConfig(), ShapeModels()).run(uuid4(), scene(), tmp_path / "boundary")
    assert package.outcome == "comparable"
    assert package.boundary_changes
    assert package.candidates == []
    assert any(c.direction == "potentially_missing" for c in package.boundary_changes)
    assert CVPackage.model_validate_json(package.model_dump_json()) == package
    provider = MockProvider(
        lambda request: pytest.fail("Boundary-only evidence must not call provider")
    )
    report = assess(
        uuid4(), package, lambda key: pytest.fail("Unnecessary read"), AssessmentOptions(), provider
    )
    assert report.status == "inconclusive"
    assert report.payment_action == "none" and report.human_review_required
    assert provider.calls == 0
    forged = package.model_dump(mode="json")
    forged["boundary_changes"][0]["before_id"] = str(uuid4())
    with pytest.raises(ValidationError):
        CVPackage.model_validate(forged)


def test_view_labels_prevent_cross_view_pairing(tmp_path):
    inputs = scene()
    inputs[0].view, inputs[1].view = "front", "back"
    package = CVPipeline(CVConfig(), ShapeModels()).run(uuid4(), inputs, tmp_path / "view")
    assert not package.pairs and package.outcome == "inconclusive"


def test_invalid_mask_abstains_and_later_run_recovers(tmp_path):
    adapter = ShapeModels(fail_first=True)
    inputs = scene()
    rejected = CVPipeline(CVConfig(), adapter).run(uuid4(), inputs, tmp_path / "rejected")
    assert rejected.outcome == "inconclusive" and adapter.closed == 1
    assert rejected.segmentation[0].status == "inconclusive"
    recovered = CVPipeline(CVConfig(), adapter).run(uuid4(), inputs, tmp_path / "recovered")
    assert recovered.outcome == "comparable" and adapter.closed == 2


def test_truncated_comparison_cannot_be_reported_as_unchanged(tmp_path):
    inputs = scene()
    inputs[1].rgb = inputs[0].rgb.copy()
    package = CVPipeline(CVConfig(), ShapeModels()).run(uuid4(), inputs, tmp_path / "truncated")
    assert not package.candidates and not package.boundary_changes
    package.metrics["candidates_truncated"] = 1
    provider = MockProvider(lambda request: pytest.fail("Incomplete comparison"))
    report = assess(
        uuid4(), package, lambda key: pytest.fail("Unnecessary read"), AssessmentOptions(), provider
    )
    assert report.status == "inconclusive" and provider.calls == 0
    assert report.payment_action == "none"
