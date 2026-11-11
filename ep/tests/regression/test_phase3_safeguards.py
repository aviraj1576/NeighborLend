from uuid import uuid4

import cv2
import numpy as np
import pytest

from ep_engine.core.exceptions import EPError
from ep_engine.cv.changes import find_changes
from ep_engine.cv.contracts import CVConfig
from ep_engine.cv.geometry import align_pair, match_pair, validate_transform


def test_rejected_similarity_is_not_reported_as_executed_matching(monkeypatch):
    monkeypatch.setattr(
        "ep_engine.cv.geometry.local_features", lambda *a: pytest.fail("Gate bypass")
    )
    rgb = np.zeros((128, 128, 3), np.uint8)
    pair, matrix = match_pair(
        uuid4(), uuid4(), rgb, rgb, rgb[:, :, 0] > 0, rgb[:, :, 0] > 0, 0.2, CVConfig()
    )
    assert pair.local_matching_evaluated is False and pair.alignment_status == "not_attempted"
    assert matrix is None and pair.identity == "uncertain"


def test_valid_overlap_threshold_applies_after_boundary_erosion():
    mask = np.zeros((128, 128), bool)
    mask[20:30, 20:120] = True
    with pytest.raises(EPError, match="overlap"):
        align_pair(np.zeros((128, 128, 3), np.uint8), mask, mask, np.eye(3), CVConfig())


def test_missing_ransac_inlier_mask_rejects_instead_of_crashing(monkeypatch):
    image = np.random.default_rng(4).integers(0, 255, (256, 256, 3), np.uint8)
    mask = np.zeros((256, 256), bool)
    mask[16:-16, 16:-16] = True
    monkeypatch.setattr(cv2, "findHomography", lambda *a: (np.eye(3), None))
    pair, matrix = match_pair(uuid4(), uuid4(), image, image, mask, mask, 1, CVConfig())
    assert matrix is None and pair.status == "inconclusive"
    assert pair.local_matching_evaluated and "unstable_geometry" in pair.reasons


def test_homography_with_projective_pole_is_rejected():
    with pytest.raises(EPError):
        validate_transform(
            np.array([[1.0, 0, 0], [0, 1, 0], [-0.01, 0, 1]]), (256, 256), (256, 256)
        )


def test_known_occlusion_is_excluded_from_local_comparison():
    before = np.random.default_rng(37).integers(40, 200, (256, 256, 3), np.uint8)
    after = before.copy()
    after[90:150, 80:140] = 0
    mask = np.zeros((256, 256), bool)
    mask[20:-20, 20:-20] = True
    visible = mask.copy()
    visible[90:150, 80:140] = False
    warped, overlap = align_pair(before, mask, visible, np.eye(3), CVConfig())
    assert not overlap[90:150, 80:140].any()
    assert find_changes(warped, after, overlap, CVConfig())[1] == []
