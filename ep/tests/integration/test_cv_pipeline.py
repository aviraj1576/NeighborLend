from uuid import uuid4

import numpy as np
import pytest

from ep_engine.cv.contracts import CVConfig, CVPackage
from ep_engine.cv.pipeline import CVPipeline, InputImage
from ep_engine.schemas.models import Box


class DeterministicModels:
    """Contract/failure injection only; never evidence of pretrained inference."""

    def segment(self, rgb, box):
        mask = np.zeros(rgb.shape[:2], bool)
        mask[20:-20, 20:-20] = True
        return mask

    def embedding(self, rgb, mask):
        return np.ones(384, np.float32)

    def metrics(self):
        return {"device": "injected-test-adapter"}

    def close(self):
        pass


@pytest.fixture
def cv_inputs():
    image = np.random.default_rng(13).integers(30, 210, (256, 256, 3), np.uint8)
    target = Box(x1=0.05, y1=0.05, x2=0.95, y2=0.95)
    return [
        InputImage(uuid4(), "before", image, "a" * 64, target),
        InputImage(uuid4(), "after", image.copy(), "b" * 64, target),
    ]


def test_connected_stages_artifacts_and_change_candidates(tmp_path, cv_inputs):
    cv_inputs[1].rgb[90:120, 100:130] = 0
    package = CVPipeline(CVConfig(), DeterministicModels()).run(
        uuid4(), cv_inputs, tmp_path / "artifacts"
    )
    assert package.outcome == "comparable"
    assert package.candidates
    assert len(package.metrics["stage_seconds"]) == 6
    assert all((tmp_path / "artifacts" / f"{item.id}.png").is_file() for item in package.artifacts)
    assert CVPackage.model_validate_json(package.model_dump_json()) == package
    assert "damage" not in package.candidates[0].observation


def test_partial_and_missing_targets_are_truthful(tmp_path, cv_inputs):
    third = InputImage(uuid4(), "after", cv_inputs[1].rgb.copy(), "c" * 64, None)
    package = CVPipeline(CVConfig(), DeterministicModels()).run(
        uuid4(), cv_inputs + [third], tmp_path / "partial"
    )
    assert package.outcome == "partially_comparable"
    assert third.id in package.unmatched_ids
    for image in cv_inputs:
        image.target = None
    package = CVPipeline(CVConfig()).run(uuid4(), cv_inputs, tmp_path / "unmatched")
    assert package.outcome == "inconclusive"
    assert package.metrics["device"] == "not_loaded"


def test_invalid_model_output_does_not_succeed(tmp_path, cv_inputs):
    from ep_engine.core.exceptions import EPError

    adapter = DeterministicModels()
    adapter.embedding = lambda rgb, mask: np.full(384, np.nan)
    with pytest.raises(EPError) as caught:
        CVPipeline(CVConfig(), adapter).run(uuid4(), cv_inputs, tmp_path / "bad")
    assert caught.value.code == "invalid_embedding"
