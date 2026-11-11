"""Deterministic behavior checks; generated pixels never establish real-photo accuracy."""

from uuid import uuid4

import cv2
import numpy as np
import pytest

from ep_engine.core.exceptions import EPError
from ep_engine.cv.changes import boundary_regions, find_changes
from ep_engine.cv.contracts import CVConfig
from ep_engine.cv.geometry import match_pair
from ep_engine.cv.quality import assess_quality
from ep_engine.cv.targeting import embedding_canvas, select_target_mask, validate_target_mask


def test_background_high_score_cannot_override_plausible_foreground():
    object_mask = np.zeros((128, 128), bool)
    object_mask[24:104, 24:104] = True
    background = ~object_mask
    selected = select_target_mask(
        np.stack([background, object_mask, background]),
        np.array([0.99, 0.75, 0.95]),
        (0.01, 0.01, 0.99, 0.99),
    )
    assert np.array_equal(selected, object_mask)
    with pytest.raises(EPError, match="No plausible"):
        select_target_mask(np.stack([background] * 3), np.ones(3), (0.01, 0.01, 0.99, 0.99))


def test_target_leakage_disconnected_masks_and_ambiguity_reject():
    mask = np.zeros((128, 128), bool)
    mask[10:50, 10:50] = True
    mask[80:120, 80:120] = True
    with pytest.raises(EPError):
        validate_target_mask(mask, (0.05, 0.05, 0.95, 0.95))
    one = np.zeros_like(mask)
    two = np.zeros_like(mask)
    one[24:88, 10:62] = True
    two[24:88, 66:118] = True
    with pytest.raises(EPError, match="Competing"):
        select_target_mask(np.stack([one, two]), np.ones(2), (0.05, 0.15, 0.95, 0.75))


def test_full_object_embedding_retains_ends_and_removes_background():
    rgb = np.full((40, 200, 3), 255, np.uint8)
    mask = np.zeros((40, 200), bool)
    mask[10:30, 5:195] = True
    rgb[10:30, 5:35] = (255, 0, 0)
    rgb[10:30, 165:195] = (0, 0, 255)
    canvas = embedding_canvas(rgb, mask)
    assert canvas.shape == (224, 224, 3)
    assert (canvas[:, :, 0] > 0.9).any() and (canvas[:, :, 2] > 0.9).any()
    assert np.allclose(canvas[0, 0], np.array([124, 116, 104]) / 255)
    changed_background = rgb.copy()
    changed_background[~mask] = 0
    assert np.array_equal(canvas, embedding_canvas(changed_background, mask))


def test_blur_quality_gate_and_recapture_guidance_are_preserved():
    blurred = np.full((256, 256, 3), 128, np.uint8)
    result = assess_quality(uuid4(), blurred, CVConfig())
    assert result.status == "needs_recapture"
    assert "blur_or_no_texture" in result.reasons
    assert result.recommendations
    assert CVConfig().min_focus == 25 and CVConfig().min_similarity == 0.65


def test_thin_scratch_survives_and_preexisting_mark_is_not_new():
    rgb = np.random.default_rng(81).integers(40, 190, (192, 192, 3), np.uint8)
    mask = np.zeros((192, 192), bool)
    mask[16:-16, 16:-16] = True
    changed = rgb.copy()
    cv2.line(changed, (60, 55), (120, 135), (0, 0, 0), 1)
    _, regions = find_changes(rgb, changed, mask, CVConfig())
    assert any(
        x <= 65 and y <= 60 and x + w >= 115 and y + h >= 130 for x, y, w, h, _, _ in regions
    )
    assert find_changes(changed, changed, mask, CVConfig())[1] == []
    exposure = np.clip(rgb.astype(float) * 1.12 + 7, 0, 255).astype(np.uint8)
    assert find_changes(rgb, exposure, mask, CVConfig())[1] == []


def test_missing_tab_boundary_is_separate_from_overlap_appearance():
    before = np.zeros((256, 256), bool)
    before[45:210, 45:190] = True
    before[90:140, 190:230] = True
    after = before.copy()
    after[90:140, 190:230] = False
    regions, notes = boundary_regions(before, after, np.eye(3), CVConfig())
    assert any(r["direction"] == "potentially_missing" for r in regions)
    assert all(r["area_pixels"] >= 16 for r in regions)
    assert notes
    assert boundary_regions(before, before, np.eye(3), CVConfig())[0] == []
    shift = np.array([[1.0, 0, 7], [0, 1.0, -4], [0, 0, 1.0]])
    translated = cv2.warpPerspective(before.astype(np.uint8), shift, (256, 256)).astype(bool)
    assert boundary_regions(before, translated, shift, CVConfig())[0] == []


def test_boundary_changes_abstain_at_crop_and_global_mask_disagreement():
    before = np.zeros((128, 128), bool)
    before[0:100, 20:100] = True
    after = before.copy()
    after[30:60, 80:100] = False
    assert boundary_regions(before, after, np.eye(3), CVConfig())[0] == []
    first = np.zeros((256, 256), bool)
    second = np.zeros_like(first)
    first[20:110, 20:110] = True
    second[145:235, 145:235] = True
    regions, notes = boundary_regions(first, second, np.eye(3), CVConfig())
    assert not regions and "mask_disagreement_or_view_change" in notes


def test_mask_jitter_without_pixel_change_cannot_claim_missing_parts():
    before = np.zeros((256, 256), bool)
    before[45:210, 45:190] = True
    before[90:140, 190:230] = True
    after_mask = before.copy()
    after_mask[90:140, 190:230] = False
    rgb = np.random.default_rng(130).integers(40, 190, (256, 256, 3), np.uint8)
    regions, notes = boundary_regions(
        before, after_mask, np.eye(3), CVConfig(), aligned_before=rgb, after=rgb
    )
    assert not regions and "boundary_without_appearance_support" in notes
    removed = rgb.copy()
    removed[90:140, 190:230] = 240
    supported, _ = boundary_regions(
        before, after_mask, np.eye(3), CVConfig(), aligned_before=rgb, after=removed
    )
    assert any(r["direction"] == "potentially_missing" for r in supported)


def test_rotation_scale_lighting_geometry_and_different_texture_abstention():
    before = np.random.default_rng(102).integers(25, 200, (256, 256, 3), np.uint8)
    mask = np.zeros((256, 256), bool)
    mask[24:232, 24:232] = True
    affine = cv2.getRotationMatrix2D((128, 128), 8, 0.92)
    after = cv2.warpAffine(before, affine, (256, 256))
    after_mask = cv2.warpAffine(mask.astype(np.uint8), affine, (256, 256)).astype(bool)
    pair, matrix = match_pair(uuid4(), uuid4(), before, after, mask, after_mask, 0.98, CVConfig())
    assert matrix is not None and pair.inliers >= 12
    unrelated = np.random.default_rng(103).integers(25, 200, (256, 256, 3), np.uint8)
    rejected, matrix = match_pair(uuid4(), uuid4(), before, unrelated, mask, mask, 0.98, CVConfig())
    assert matrix is None and rejected.identity == "uncertain"


def test_similarity_fallback_retains_correspondence_support(monkeypatch):
    rgb = np.random.default_rng(116).integers(25, 200, (256, 256, 3), np.uint8)
    mask = np.zeros((256, 256), bool)
    mask[24:-24, 24:-24] = True
    monkeypatch.setattr(
        cv2,
        "findHomography",
        lambda src, dst, *args: (np.zeros((3, 3)), np.ones((len(src), 1), np.uint8)),
    )
    pair, matrix = match_pair(uuid4(), uuid4(), rgb, rgb, mask, mask, 0.99, CVConfig())
    assert matrix is not None and pair.geometry_model == "similarity"
    assert pair.inliers >= 12 and pair.symmetric_reprojection_error < 1
    assert min(pair.source_coverage, pair.target_coverage) >= 0.03


def test_quarter_turn_does_not_create_raster_damage_proposals():
    from ep_engine.cv.geometry import align_pair

    before = np.random.default_rng(121).integers(30, 200, (256, 256, 3), np.uint8)
    mask = np.zeros((256, 256), bool)
    mask[24:-24, 24:-24] = True
    after = np.rot90(before).copy()
    after_mask = np.rot90(mask).copy()
    pair, matrix = match_pair(uuid4(), uuid4(), before, after, mask, after_mask, 0.99, CVConfig())
    assert matrix is not None and pair.inliers >= 12
    aligned, overlap = align_pair(before, mask, after_mask, matrix, CVConfig())
    assert np.abs(aligned[overlap].astype(float) - after[overlap]).mean() < 1
    assert find_changes(aligned, after, overlap, CVConfig())[1] == []
