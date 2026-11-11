"""Generated software controls; not physical-damage accuracy measurements."""

import hashlib
from types import SimpleNamespace
from uuid import uuid4

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from ep_engine.cv.artifacts import ArtifactWriter
from ep_engine.cv.changes import find_changes
from ep_engine.cv.pipeline import InputImage
from ep_engine.schemas.models import Box
from ep_engine.v3.config import V3Config
from ep_engine.v3.matching import verify_correspondences
from ep_engine.v31.api import inspect_inputs
from ep_engine.v31.contracts import InspectionReport
from ep_engine.v31.coordinates import crop_frame, original_transform, resize_frame
from ep_engine.v31.matching import cropped_matches, local_surfaces, object_crop
from ep_engine.v31.pipeline import InspectionPipeline
from ep_engine.v31.surfaces import observe_surfaces


@pytest.mark.parametrize("turns", range(4))
def test_cropped_rotation_preserves_original_coordinates(turns):
    image = np.zeros((240, 320, 3), np.uint8)
    mask = np.zeros((240, 320), bool)
    mask[30:180, 80:270] = True
    _, cropmask, offset = object_crop(image, mask)
    points = np.array([[50.0, 40.0], [100.0, 60.0], [140.0, 80.0]], np.float32)
    h, w = cropmask.shape
    rotated = [
        points,
        np.column_stack((points[:, 1], w - 1 - points[:, 0])),
        np.column_stack((w - 1 - points[:, 0], h - 1 - points[:, 1])),
        np.column_stack((h - 1 - points[:, 1], points[:, 0])),
    ][turns]
    src, dst = cropped_matches(lambda *args: (points, rotated), image, image, mask, mask, turns)
    assert np.allclose(src, points + offset)
    assert np.allclose(dst, points + offset)


def test_fixed_local_partition_does_not_extrapolate_to_whole_object():
    image = np.zeros((300, 300, 3), np.uint8)
    mask = np.zeros((300, 300), bool)
    mask[20:280, 20:280] = True
    src = np.array([(x, y) for x in range(35, 270, 22) for y in range(35, 270, 22)], np.float32)
    dst = src.copy()
    dst[:, 0] += np.where(src[:, 0] < 150, -8, 8)
    dst[:, 1] += np.where(src[:, 1] < 150, -8, 8)
    regions = local_surfaces(src, dst, image, mask, mask, V3Config(), verify_correspondences)
    assert len(regions) == 4
    for region in regions:
        assert 64 < region["overlap"].sum() < 0.25 * mask.sum()
        assert region["support"]["inlier_ratio"] > 0.9
        assert region["matches"] >= 12


def fixture_surface(tmp_path, changed):
    before, after = uuid4(), uuid4()
    original = np.full((1024, 1024, 3), 150, np.uint8)
    modified = original.copy()
    if changed:
        modified[400:620, 500] = 100  # Contrast is diluted below threshold in the 4x thumbnail.
    images = {
        before: cv2.resize(original, (256, 256), interpolation=cv2.INTER_AREA),
        after: cv2.resize(modified, (256, 256), interpolation=cv2.INTER_AREA),
    }
    mask = np.zeros((256, 256), bool)
    mask[20:236, 20:236] = True
    config = V3Config(appearance_backend="opencv")
    pipeline = InspectionPipeline(config)
    pipeline.images = images
    pipeline.masks = {before: mask, after: mask}
    pipeline.geometries = {(before, after): np.eye(3)}
    pipeline.aligned = {(before, after): (images[before], mask)}
    pipeline.writer = ArtifactWriter(tmp_path, [before, after])
    pair = SimpleNamespace(
        before_id=before,
        after_id=after,
        status="comparable",
        inliers=30,
        inlier_ratio=1.0,
        symmetric_reprojection_error=0.0,
    )
    package = SimpleNamespace(pairs=[pair], artifacts=[])
    rows = [
        InputImage(
            key,
            stage,
            images[key],
            hashlib.sha256(rgb).hexdigest(),
            None,
            original_size=(1024, 1024),
            original_rgb=rgb,
        )
        for key, stage, rgb in ((before, "before", original), (after, "after", modified))
    ]
    return pipeline, package, rows, mask


def test_original_scan_detects_thin_edit_missing_from_thumbnail(tmp_path):
    pipeline, package, rows, mask = fixture_surface(tmp_path, True)
    _, coarse = find_changes(rows[0].rgb, rows[1].rgb, mask, pipeline.config)
    assert not coarse
    observations = observe_surfaces(pipeline, package, rows, 1)
    assert len(observations) == 1
    observation = observations[0]
    assert observation.scope == "original_resolution_tile"
    assert any(
        box.x1 <= 500 / 1024 <= box.x2 and box.y1 <= 500 / 1024 <= box.y2
        for box in observation.appearance_regions
    )
    assert observation.sampling_floor_source_pixels == 2
    assert len(package.artifacts) == 4


def test_original_scan_repeat_and_zero_budget_are_safe(tmp_path):
    pipeline, package, rows, _ = fixture_surface(tmp_path, False)
    assert observe_surfaces(pipeline, package, rows, 0) == []
    assert not pipeline.writer.records
    observations = observe_surfaces(pipeline, package, rows, 1)
    assert len(observations) == 1 and not observations[0].appearance_regions


def test_surface_provenance_validation_and_original_inputs_immutable(tmp_path):
    class Models:
        def segment(self, rgb, box):
            mask = np.zeros(rgb.shape[:2], bool)
            mask[20:-20, 20:-20] = True
            return mask

        def embedding(self, *args):
            return np.ones(384, np.float32)

        def close(self):
            pass

        def metrics(self):
            return {}

    original = np.random.default_rng(47).integers(20, 230, (768, 768, 3), np.uint8)
    rows = [
        InputImage(
            uuid4(),
            stage,
            cv2.resize(original, (256, 256)),
            hashlib.sha256(original).hexdigest(),
            Box(x1=0.05, y1=0.05, x2=0.95, y2=0.95),
            original_size=(768, 768),
            original_rgb=original.copy(),
        )
        for stage in ("before", "after")
    ]
    report = inspect_inputs(
        uuid4(),
        rows,
        tmp_path / "artifacts",
        V3Config(appearance_backend="opencv"),
        models=Models(),
    )
    assert report.surface_observations
    assert all(not r.appearance_regions for r in report.surface_observations)
    assert np.array_equal(rows[0].original_rgb, original)
    payload = report.model_dump(mode="json")
    payload["surface_observations"][0]["artifact_ids"][0] = str(uuid4())
    with pytest.raises(ValidationError, match="artifact frame"):
        InspectionReport.model_validate(payload)


def test_source_frame_composition_preserves_pixel_centers_at_unequal_resolutions():
    source = (1200, 1600)
    first, second = (300, 400), (600, 800)
    processed = resize_frame(first, second)
    assert np.allclose(original_transform(processed, first, second, source, source), np.eye(3))
    # A crop downsample places its first sample at the center of four source pixels.
    transform = crop_frame((100, 200, 500, 600), (100, 100))
    point = cv2.perspectiveTransform(np.array([[[101.5, 201.5]]]), transform)[0, 0]
    assert np.allclose(point, [0, 0])


def test_segmentation_reuse_is_content_target_bound_bounded_and_defensively_copied(monkeypatch):
    from collections import OrderedDict

    from ep_engine.cv.models import NativeModels
    from ep_engine.v31.models import InspectionModels

    calls = []

    def segment(self, rgb, box):
        calls.append(1)
        mask = np.zeros(rgb.shape[:2], bool)
        mask[2:-2, 2:-2] = True
        return mask

    monkeypatch.setattr(NativeModels, "segment", segment)
    model = InspectionModels.__new__(InspectionModels)
    model.mask_cache = OrderedDict()
    model.mask_cache_hits = 0
    rgb = np.zeros((16, 16, 3), np.uint8)
    box = (0.1, 0.1, 0.9, 0.9)
    first = model.segment(rgb, box)
    first[:] = False
    assert model.segment(rgb.copy(), box).any() and len(calls) == 1
    model.segment(rgb, (0.2, 0.2, 0.8, 0.8))
    assert len(calls) == 2
    for value in range(1, 15):
        model.segment(np.full_like(rgb, value), box)
    assert len(model.mask_cache) == 12
    model.segment(rgb, box)
    assert len(calls) == 17
