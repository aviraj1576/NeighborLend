from uuid import uuid4

import cv2
import numpy as np

from ep_engine.cv.contracts import CVConfig
from ep_engine.cv.quality import assess_quality


def test_quality_measures_focus_exposure_and_resolution():
    rng = np.random.default_rng(41)
    sharp = rng.integers(20, 230, (256, 256, 3), np.uint8)
    config = CVConfig()
    good = assess_quality(uuid4(), sharp, config)
    blurred = assess_quality(uuid4(), cv2.GaussianBlur(sharp, (31, 31), 8), config)
    assert good.status == "usable"
    assert blurred.focus_variance < good.focus_variance
    assert blurred.status == "needs_recapture"
    for rgb, reason in (
        (np.zeros_like(sharp), "underexposed"),
        (np.full_like(sharp, 255), "overexposed"),
    ):
        result = assess_quality(uuid4(), rgb, config)
        assert result.status == "needs_recapture"
        assert reason in result.reasons
    assert "low_resolution" in assess_quality(uuid4(), sharp[:40, :40], config).reasons


def test_mask_visibility_and_threshold_configuration():
    rgb = np.random.default_rng(22).integers(30, 220, (128, 128, 3), np.uint8)
    mask = np.ones((128, 128), bool)
    result = assess_quality(uuid4(), rgb, CVConfig(min_focus=0, min_contrast=0), mask)
    assert result.object_fraction == 1
    assert result.touches_frame
    assert "possible_cropping" in result.reasons
