"""Engineering controls only; generated edits are never real damage ground truth."""

import hashlib
from uuid import uuid4

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from ep_engine.core.exceptions import EPError
from ep_engine.cv.contracts import CVPackage
from ep_engine.cv.geometry import align_pair
from ep_engine.cv.pipeline import InputImage
from ep_engine.schemas.models import Box
from ep_engine.v3.config import V3Config
from ep_engine.v3.matching import HybridMatcher
from ep_engine.v3.pipeline import V3Pipeline
from ep_engine.v31.api import inspect_inputs
from ep_engine.v31.contracts import InspectionReport, InspectionRequest
from ep_engine.v31.pipeline import InspectionPipeline


class Models:
    def segment(self, rgb, box):
        mask = np.zeros(rgb.shape[:2], bool)
        mask[20:-20, 20:-20] = True
        return mask

    def embedding(self, rgb, mask):
        return np.ones(384, np.float32)

    def metrics(self):
        return {"device": "injected_test_adapter"}

    def close(self):
        pass


def inputs(views=1):
    result = []
    for view in range(views):
        image = np.random.default_rng(13 + view).integers(30, 210, (256, 256, 3), np.uint8)
        for stage in ("before", "after"):
            result.append(
                InputImage(
                    uuid4(),
                    stage,
                    image.copy(),
                    hashlib.sha256(image).hexdigest(),
                    Box(x1=0.05, y1=0.05, x2=0.95, y2=0.95),
                    view=str(view),
                )
            )
    return result


@pytest.mark.parametrize("similarity,expected", [(1.000000119, 1), (-1.000000119, -1)])
def test_hybrid_cosine_roundoff_is_bounded_before_both_pair_constructors(similarity, expected):
    image = inputs()[0].rgb
    mask = Models().segment(image, None)
    pipeline = HybridMatcher(
        V3Config(compare_matchers=True),
        learned=lambda *args: (np.empty((0, 2), np.float32), np.empty((0, 2), np.float32)),
    )
    pair, _ = pipeline(uuid4(), uuid4(), image, image, mask, mask, similarity, V3Config())
    assert pair.cosine_similarity == expected


@pytest.mark.parametrize("similarity", [np.nan, np.inf, -np.inf])
def test_nonfinite_cosine_rejected(similarity):
    image = inputs()[0].rgb
    mask = Models().segment(image, None)
    with pytest.raises(EPError) as error:
        HybridMatcher(V3Config())(
            uuid4(), uuid4(), image, image, mask, mask, similarity, V3Config()
        )
    assert error.value.code == "invalid_embedding"


def test_secondary_alignment_failure_preserves_unaffected_view(tmp_path, monkeypatch):
    pipeline = V3Pipeline(V3Config(appearance_backend="opencv"), Models())
    original = pipeline._find_changes
    calls = []

    def fail_first(*args):
        calls.append(1)
        if len(calls) == 1:
            raise EPError(422, "insufficient_overlap", "Injected secondary alignment failure")
        return original(*args)

    monkeypatch.setattr(pipeline, "_find_changes", fail_first)
    package = pipeline.run(uuid4(), inputs(2), tmp_path / "artifacts")
    assert package.outcome == "partially_comparable"
    assert sum(p.status == "comparable" for p in package.pairs) == 1
    assert any("insufficient_overlap" in p.reasons for p in package.pairs)
    assert len(package.unmatched_ids) == 2
    assert CVPackage.model_validate_json(package.model_dump_json()) == package


@pytest.mark.parametrize("stage", ["_align_pair", "_find_changes"])
def test_unexpected_programming_errors_are_not_swallowed(tmp_path, monkeypatch, stage):
    pipeline = V3Pipeline(V3Config(appearance_backend="opencv"), Models())

    def bug(*args):
        raise RuntimeError("Programming defect")

    monkeypatch.setattr(pipeline, stage, bug)
    with pytest.raises(EPError) as error:
        pipeline.run(uuid4(), inputs(), tmp_path / stage)
    assert error.value.code == "stage_failed"
    assert isinstance(error.value.__cause__, RuntimeError)


def test_strict_nested_telemetry_rejects_nonfinite_values(tmp_path):
    report = inspect_inputs(
        uuid4(),
        inputs(),
        tmp_path / "artifacts",
        V3Config(appearance_backend="opencv"),
        models=Models(),
    )
    payload = report.model_dump(mode="json")
    payload["runtime"]["nested"] = {"bad": [float("nan")]}
    with pytest.raises(ValidationError, match="Nonfinite"):
        InspectionReport.model_validate(payload)
    package = report.cv_package.model_dump(mode="json")
    package["metrics"]["nested"] = {"bad": [float("inf")]}
    with pytest.raises(ValidationError, match="Nonfinite"):
        CVPackage.model_validate(package)


def test_repeat_has_no_proposals_or_damage_attribution_and_truthful_scope(tmp_path):
    report = inspect_inputs(
        uuid4(),
        inputs(),
        tmp_path / "artifacts",
        V3Config(appearance_backend="opencv"),
        models=Models(),
    )
    assert report.cv_package.outcome == "comparable"
    assert not report.cv_package.candidates and not report.cv_package.boundary_changes
    assert report.views[0].observation == "no_localized_change_detected"
    assert report.views[0].unassessed_after_fraction > 0
    assert report.identity[0].visual_relation == "same_capture"
    assert not report.physical_identity_verified and not report.possible_damage_hypotheses
    assert (
        report.payment_action == "none"
        and report.fusion["whole_object_condition"] == "inconclusive"
    )
    assert InspectionReport.model_validate_json(report.model_dump_json()) == report


def test_high_embedding_never_proves_physical_identity_on_different_texture(tmp_path):
    rows = inputs()
    rows[1].rgb = inputs(2)[-1].rgb
    report = inspect_inputs(
        uuid4(),
        rows,
        tmp_path / "artifacts",
        V3Config(appearance_backend="opencv"),
        models=Models(),
    )
    assert not report.physical_identity_verified
    assert all(r.status == "identity_unverified" for r in report.identity)
    assert not report.possible_damage_hypotheses


def test_explicit_instance_mismatch_abstains_even_for_identical_pixels(tmp_path):
    rows = inputs()
    report = inspect_inputs(
        uuid4(),
        rows,
        tmp_path / "artifacts",
        V3Config(appearance_backend="opencv"),
        models=Models(),
        instance_ids={rows[0].id: "left", rows[1].id: "right"},
    )
    assert report.cv_package.outcome == "inconclusive"
    assert "ambiguous_instance_assignment" in report.cv_package.pairs[0].reasons


def test_independently_movable_components_do_not_receive_one_global_warp(tmp_path):
    class MultiModels(Models):
        def segment(self, rgb, box):
            mask = np.zeros(rgb.shape[:2], bool)
            mask[30:225, 24:180] = True
            mask[30:225, 200:231] = True
            return mask

    rows = inputs()
    rows[1].rgb[40:80, 40:80] = 0
    report = inspect_inputs(
        uuid4(),
        rows,
        tmp_path / "artifacts",
        V3Config(appearance_backend="opencv"),
        models=MultiModels(),
    )
    assert report.cv_package.outcome == "inconclusive"
    assert all(r.significant_mask_components == 2 for r in report.instances)
    assert not report.cv_package.candidates


def test_duplicate_views_are_grouped_without_independent_support_claim(tmp_path):
    rows = inputs(2)
    rows[2].rgb, rows[3].rgb = rows[0].rgb.copy(), rows[1].rgb.copy()
    report = inspect_inputs(
        uuid4(),
        rows,
        tmp_path / "artifacts",
        V3Config(appearance_backend="opencv"),
        models=Models(),
    )
    assert len(report.fusion["observation_groups"]) == 1
    assert len(report.fusion["observation_groups"][0]) == 2
    assert report.fusion["independent_support_count"] is None


def test_original_detail_crops_are_bounded_and_cited(tmp_path):
    rows = inputs()
    for row in rows:
        row.rgb = cv2.resize(row.rgb, (768, 768), interpolation=cv2.INTER_NEAREST)
    rows[1].rgb[300:340, 320:360] = 0
    report = inspect_inputs(
        uuid4(),
        rows,
        tmp_path / "artifacts",
        V3Config(max_side=256, appearance_backend="opencv"),
        models=Models(),
        high_resolution_crops=1,
    )
    assert len(report.detail_crops) == 1
    crop = report.detail_crops[0]
    assert crop.width <= 1024 and crop.height <= 1024
    assert crop.sampling_floor_source_pixels >= 2
    assert set(crop.artifact_ids).issubset({r.id for r in report.cv_package.artifacts})
    assert not report.possible_damage_hypotheses


@pytest.mark.parametrize("turns", [1, 2, 3])
def test_quarter_turn_coordinates_and_mask_overlap(turns):
    image = inputs()[0].rgb[:192, :256]
    mask = np.zeros(image.shape[:2], bool)
    mask[20:-20, 20:-20] = True
    height, width = image.shape[:2]
    matrices = {
        1: np.array([[0, 1, 0], [-1, 0, width - 1], [0, 0, 1.0]]),
        2: np.array([[-1, 0, width - 1], [0, -1, height - 1], [0, 0, 1.0]]),
        3: np.array([[0, -1, height - 1], [1, 0, 0], [0, 0, 1.0]]),
    }
    after = np.rot90(image, turns).copy()
    after_mask = np.rot90(mask, turns).copy()
    aligned, overlap = align_pair(image, mask, after_mask, matrices[turns], V3Config())
    assert np.array_equal(aligned[overlap], after[overlap])
    assert overlap.sum() > 0.8 * after_mask.sum()


def test_request_forbids_unknown_fields_and_missing_stages():
    with pytest.raises(ValidationError):
        InspectionRequest.model_validate(
            {"inspection_id": str(uuid4()), "evidence": [], "payment_action": "deduct"}
        )


def test_object_sampling_bound_covers_dense_local_jacobians_and_preserves_identity():
    mask = np.zeros((768, 768), bool)
    mask[300:500, 270:510] = True
    pipeline = InspectionPipeline(V3Config())
    assert pipeline._sampling_scale(np.eye(3), mask) == 1
    matrix = np.array([[1.0, 0.02, 6], [0.01, 1.0, 4], [-0.0005, 0, 1]])
    bound = 1 / pipeline._sampling_scale(matrix, mask)
    ys, xs = np.where(mask)
    for x, y in zip(xs[::79], ys[::79], strict=True):
        p = matrix @ np.array([x, y, 1.0])
        jacobian = (matrix[:2, :2] * p[2] - np.outer(p[:2], matrix[2, :2])) / p[2] ** 2
        assert np.linalg.norm(jacobian, ord=2) <= bound + 1e-12
    assert pipeline._sampling_scale(matrix, mask) > pipeline._comparison_scale(matrix, mask.shape)


def test_selective_half_turn_fallback_returns_original_frame_coordinates(tmp_path):
    rows = inputs()
    rows[1].rgb = np.rot90(rows[0].rgb, 2).copy()
    points = np.array([(x, y) for x in range(40, 220, 30) for y in range(40, 220, 30)], np.float32)
    calls = []

    def learned(before, after, mask0, mask1):
        calls.append(1)
        if len(calls) == 1:
            return np.empty((0, 2), np.float32), np.empty((0, 2), np.float32)
        return points.copy(), points.copy()

    pipeline = InspectionPipeline(V3Config(appearance_backend="opencv"), Models(), learned)
    before, after = rows
    mask = Models().segment(before.rgb, None)
    pair, matrix = pipeline._instance_match(
        before.id,
        after.id,
        before.rgb,
        after.rgb,
        mask,
        mask,
        0.99,
        pipeline.config,
        (([], None), ([], None)),
    )
    assert matrix is not None and len(calls) == 2 and "rot180" in pair.method
    predicted = cv2.perspectiveTransform(points[None], matrix)[0]
    assert np.allclose(predicted, 255 - points, atol=0.01)
    assert pair.symmetric_reprojection_error < 0.01


def test_half_turn_fallback_never_bypasses_embedding_gate():
    rows = inputs()
    image = rows[0].rgb
    mask = Models().segment(image, None)

    def forbidden(*args):
        pytest.fail("Inconsistent embedding must not invoke learned rotations")

    pipeline = InspectionPipeline(V3Config(), Models(), forbidden)
    pair, matrix = pipeline._instance_match(
        rows[0].id, rows[1].id, image, image, mask, mask, 0.1, pipeline.config
    )
    assert matrix is None and not pair.local_matching_evaluated


def test_touching_instance_lobes_abstain_without_changing_segmentation(tmp_path):
    class TouchingModels(Models):
        def segment(self, rgb, box):
            mask = np.zeros(rgb.shape[:2], np.uint8)
            cv2.ellipse(mask, (80, 128), (45, 100), 0, 0, 360, 1, -1)
            cv2.ellipse(mask, (176, 128), (45, 100), 0, 0, 360, 1, -1)
            mask[120:136, 100:160] = 1
            return mask.astype(bool)

    rows = inputs()
    rows[1].rgb[80:100, 70:90] = 0
    report = inspect_inputs(
        uuid4(),
        rows,
        tmp_path / "artifacts",
        V3Config(appearance_backend="opencv"),
        models=TouchingModels(),
    )
    assert report.cv_package.outcome == "inconclusive"
    assert len(report.cv_package.segmentation) == 2
    assert all(r.status == "segmented" for r in report.cv_package.segmentation)
    assert all(r.significant_mask_components == 2 for r in report.instances)
    assert (
        "multiple_movable_instances_require_separate_targets" in report.cv_package.pairs[0].reasons
    )
    assert not report.cv_package.candidates
