"""Actual CUDA parity tests. Generated controls establish behavior, never damage accuracy."""

import os

import cv2
import numpy as np
import pytest

from ep_engine.cv.changes import find_changes
from ep_engine.cv.geometry import align_pair
from ep_engine.v3.config import V3Config
from ep_engine.v3.gpu import align_cuda, appearance_cuda

pytestmark = [
    pytest.mark.real_inference,
    pytest.mark.skipif(
        os.environ.get("EP_RUN_V3_CUDA") != "1", reason="Opt in with EP_RUN_V3_CUDA=1"
    ),
]


@pytest.mark.parametrize("kind", ["identity", "translation", "quarter_turn", "perspective"])
def test_cuda_warp_preserves_pixel_frame_and_excludes_uncovered_regions(kind):
    before = np.random.default_rng(813).integers(20, 200, (256, 256, 3), np.uint8)
    mask = np.zeros((256, 256), bool)
    mask[24:-24, 24:-24] = True
    matrices = {
        "identity": np.eye(3),
        "translation": np.array([[1.0, 0, 8], [0, 1, -6], [0, 0, 1]]),
        "quarter_turn": np.array([[0.0, 1, 0], [-1, 0, 255], [0, 0, 1]]),
        "perspective": np.array([[1.0, 0.01, 3], [0.008, 1, -2], [0.00005, 0.00001, 1]]),
    }
    matrix = matrices[kind]
    after_mask = cv2.warpPerspective(mask.astype(np.uint8), matrix, (256, 256)).astype(bool)
    cpu, overlap0 = align_pair(before, mask, after_mask, matrix, V3Config())
    gpu, overlap1 = align_cuda(before, mask, after_mask, matrix, V3Config())
    assert (overlap0 & overlap1).sum() / (overlap0 | overlap1).sum() > 0.99
    shared = overlap0 & overlap1
    assert np.abs(cpu[shared].astype(float) - gpu[shared]).mean() < 1
    if kind != "perspective":
        assert find_changes(cpu, gpu, shared, V3Config())[1] == []


@pytest.mark.parametrize("kind", ["unchanged", "lighting", "thin_crack", "scratch", "preexisting"])
def test_cuda_appearance_matches_cpu_candidates_and_uncertainty(kind):
    before = np.random.default_rng(814).integers(40, 180, (256, 256, 3), np.uint8)
    after = before.copy()
    mask = np.zeros((256, 256), bool)
    mask[24:-24, 24:-24] = True
    if kind == "lighting":
        after = np.clip(before.astype(float) * 1.1 + 8, 0, 255).astype(np.uint8)
    if kind in {"thin_crack", "scratch", "preexisting"}:
        cv2.line(after, (65, 55), (120, 190), (0, 0, 0), 1 if kind == "thin_crack" else 3)
    if kind == "preexisting":
        before = after.copy()
    map0, regions0 = find_changes(before, after, mask, V3Config())
    map1, regions1 = appearance_cuda(before, after, mask, V3Config())
    assert np.max(np.abs(map0 - map1)) < 1e-4
    assert [r[:5] for r in regions0] == [r[:5] for r in regions1]
    assert bool(regions1) is (kind in {"thin_crack", "scratch"})
