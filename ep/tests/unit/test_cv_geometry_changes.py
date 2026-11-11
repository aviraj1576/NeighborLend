from uuid import uuid4

import cv2
import numpy as np
import pytest

from ep_engine.core.exceptions import EPError
from ep_engine.cv.changes import find_changes, ssim_map
from ep_engine.cv.contracts import CVConfig
from ep_engine.cv.geometry import align_pair, local_features, match_pair, validate_transform


def test_translation_alignment_and_blank_rejection():
    rng = np.random.default_rng(6)
    image = rng.integers(20, 230, (256, 256, 3), np.uint8)
    mask = np.zeros((256, 256), bool)
    mask[24:232, 24:232] = True
    transform = np.array([[1.0, 0, 6], [0, 1, -4], [0, 0, 1]])
    after = cv2.warpPerspective(image, transform, (256, 256))
    after_mask = cv2.warpPerspective(mask.astype(np.uint8), transform, (256, 256)).astype(bool)
    pair, geometry = match_pair(uuid4(), uuid4(), image, after, mask, after_mask, 0.98, CVConfig())
    assert pair.inliers >= 12
    assert pair.homography[0][2] == pytest.approx(6, abs=1)
    warped, overlap = align_pair(image, mask, after_mask, geometry, CVConfig())
    assert overlap.sum() > 30000
    assert np.abs(warped[overlap].astype(float) - after[overlap]).mean() < 5
    blank = np.zeros_like(image)
    rejected, _ = match_pair(uuid4(), uuid4(), blank, blank, mask, mask, 0.99, CVConfig())
    assert rejected.status == "inconclusive"
    assert "insufficient_correspondence" in rejected.reasons


@pytest.mark.parametrize(
    "matrix", [np.zeros((3, 3)), np.eye(2), np.full((3, 3), np.nan), np.diag([100.0, 100.0, 1.0])]
)
def test_degenerate_geometry_is_rejected(matrix):
    with pytest.raises(EPError):
        validate_transform(matrix, (256, 256), (256, 256))


def test_overlap_and_low_similarity_fail_closed():
    mask = np.zeros((128, 128), bool)
    mask[4:30, 4:30] = True
    other = np.zeros_like(mask)
    other[90:110, 90:110] = True
    with pytest.raises(EPError):
        align_pair(np.zeros((128, 128, 3), np.uint8), mask, other, np.eye(3), CVConfig())
    assert local_features(np.zeros((32, 32, 3), np.uint8), np.ones((32, 32), bool))[1] is None


def test_masked_ssim_illumination_and_local_change():
    base = np.random.default_rng(8).integers(40, 180, (128, 128, 3), np.uint8)
    overlap = np.zeros((128, 128), bool)
    overlap[12:116, 12:116] = True
    assert np.allclose(ssim_map(np.zeros((20, 20), np.float32), np.zeros((20, 20), np.float32)), 1)
    _, regions = find_changes(base, base + 10, overlap, CVConfig())
    assert regions == []
    changed = base.copy()
    changed[45:70, 50:80] = 0
    difference, regions = find_changes(base, changed, overlap, CVConfig())
    assert difference.shape == overlap.shape
    assert any(x <= 50 and y <= 45 and x + w >= 80 and y + h >= 70 for x, y, w, h, _, _ in regions)
    changed = base.copy()
    changed[:8] = 0
    assert find_changes(base, changed, overlap, CVConfig())[1] == []
