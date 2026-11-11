from uuid import uuid4

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from ep_engine.core.exceptions import EPError
from ep_engine.cv.geometry import local_features
from ep_engine.v3.config import V3Config
from ep_engine.v3.matching import HybridMatcher, filter_correspondences, verify_correspondences
from ep_engine.v3.pipeline import V3Pipeline


def fixture_pair():
    image = np.random.default_rng(47).integers(20, 230, (256, 256, 3), np.uint8)
    mask = np.zeros((256, 256), bool)
    mask[16:240, 16:240] = True
    points = np.array([(x, y) for x in range(32, 225, 32) for y in range(32, 225, 32)], np.float32)
    return image, mask, points


def test_optional_model_requires_local_hashed_checkpoint(tmp_path):
    with pytest.raises(ValidationError):
        V3Config(learned_matcher="loftr")
    with pytest.raises(ValidationError):
        V3Config(
            learned_matcher="loftr",
            checkpoint=tmp_path / "untrusted.pt",
            checkpoint_sha256="0" * 64,
        )


def test_correspondences_cannot_inflate_support_or_match_background():
    _, mask, points = fixture_pair()
    src = np.vstack((points, points, [[-1, 20], [255, 255]]))
    dst = src.copy()
    a, b = filter_correspondences(src, dst, np.ones(len(src)), mask, mask)
    assert len(a) == len(points) == len(b)
    with pytest.raises(EPError, match="Invalid learned"):
        filter_correspondences(np.full((12, 2), np.nan), points[:12], np.ones(12), mask, mask)


def test_bidirectional_geometry_and_spatial_support():
    _, mask, points = fixture_pair()
    matrix, support, reason = verify_correspondences(
        points, points + (3, -2), mask, mask, V3Config()
    )
    assert reason is None
    assert support["inliers"] == len(points)
    assert support["symmetric_reprojection_error"] < 0.01
    assert np.allclose(matrix[:2, 2], [3, -2], atol=0.01)
    tiny = points * 0.001 + 120
    assert verify_correspondences(tiny, tiny, mask, mask, V3Config())[0] is None


def test_weak_rootsift_can_use_learned_geometry_and_reject_invalid_alternative():
    image, mask, points = fixture_pair()
    matcher = HybridMatcher(V3Config(), learned=lambda *args: (points, points))
    pair, matrix = matcher(
        uuid4(), uuid4(), image, image, mask, mask, 0.99, V3Config(), (([], None), ([], None))
    )
    assert matrix is not None and "loftr" in pair.method
    assert pair.inliers == len(points)
    assert len(matcher.records[0]["attempts"]) == 2
    matcher = HybridMatcher(V3Config(), learned=lambda *args: (points, points * 0 + 10))
    pair, matrix = matcher(
        uuid4(), uuid4(), image, image, mask, mask, 0.99, V3Config(), (([], None), ([], None))
    )
    assert matrix is None and pair.identity == "uncertain"


def test_visual_similarity_gate_never_invokes_learned_matcher():
    image, mask, _ = fixture_pair()

    def forbidden(*args):
        pytest.fail("Inconsistent embedding must abstain before learned matching")

    matcher = HybridMatcher(V3Config(compare_matchers=True), learned=forbidden)
    pair, matrix = matcher(uuid4(), uuid4(), image, image, mask, mask, 0.2, V3Config())
    assert matrix is None and not pair.local_matching_evaluated


def test_strong_rootsift_retained_when_learned_geometry_is_invalid():
    image, mask, points = fixture_pair()
    config = V3Config(compare_matchers=True)
    matcher = HybridMatcher(config, learned=lambda *args: (points, points * 0))
    pair, matrix = matcher(
        uuid4(),
        uuid4(),
        image,
        image,
        mask,
        mask,
        0.99,
        config,
        (local_features(image, mask), local_features(image, mask)),
    )
    assert matrix is not None and "rootsift" in pair.method
    assert matcher.records[0]["attempts"][1]["valid"] is False


def test_gpu_unavailable_falls_back_without_hiding_invalid_overlap(monkeypatch):
    pipeline = V3Pipeline(V3Config())

    def unavailable(*args):
        raise EPError(503, "cuda_unavailable", "No GPU")

    assert pipeline._gpu_or_cpu("test", unavailable, lambda: "cpu") == "cpu"
    assert pipeline.fallbacks == [{"operation": "test", "reason": "cuda_unavailable"}]

    def invalid(*args):
        raise EPError(422, "insufficient_overlap", "No support")

    with pytest.raises(EPError):
        pipeline._gpu_or_cpu("test", invalid, lambda: pytest.fail("Must abstain"))


def test_learned_visualization_supports_missing_rootsift_descriptors():
    image, _, points = fixture_pair()
    pipeline = V3Pipeline(V3Config())
    before, after = uuid4(), uuid4()
    pipeline.images = {before: image, after: image}
    pipeline.hybrid.correspondences[(before, after)] = points, points
    result = pipeline._match_visualization(before, after, np.eye(3))
    assert result.shape == (256, 512, 3)
    assert cv2.countNonZero(cv2.cvtColor(result, cv2.COLOR_RGB2GRAY)) > 0


def test_standalone_v3_pipeline_retains_structured_evidence_and_financial_neutrality(tmp_path):
    import hashlib

    from ep_engine.cv.pipeline import InputImage
    from ep_engine.schemas.models import Box

    image, mask, _ = fixture_pair()

    class Models:
        def segment(self, rgb, box):
            return mask.copy()

        def embedding(self, rgb, object_mask):
            return np.ones(384, np.float32)

        def metrics(self):
            return {"device": "injected_test_adapter"}

        def close(self):
            pass

    target = Box(x1=0.04, y1=0.04, x2=0.96, y2=0.96)
    inputs = [
        InputImage(uuid4(), stage, image.copy(), hashlib.sha256(image).hexdigest(), target)
        for stage in ("before", "after")
    ]
    pipeline = V3Pipeline(V3Config(appearance_backend="opencv"), Models())
    result = pipeline.run(uuid4(), inputs, tmp_path / "artifacts")
    assert result.outcome == "comparable" and not result.candidates
    assert result.pairs[0].method == "dinov2_rootsift_bidirectional_v3"
    assert result.metrics["v3"]["payment_action"] == "none"
    assert result.human_review_required is True
    assert result.models["algorithm_revision"] == "ep-v3.1-advisory"
    assert {a.kind for a in result.artifacts} >= {
        "feature_matches",
        "valid_overlap",
        "difference_map",
    }
    # Reusing the pipeline must not mutate an already returned evidence package.
    pipeline.hybrid.records.clear()
    assert len(result.metrics["v3"]["matching"]) == 1


def test_embedding_cache_is_content_bound_bounded_and_returns_defensive_copies(monkeypatch):
    from ep_engine.cv.models import NativeModels
    from ep_engine.v3.pipeline import CachedModels

    monkeypatch.setattr(
        NativeModels, "__init__", lambda self, device: setattr(self, "device", device)
    )
    monkeypatch.setattr(
        "ep_engine.v3.pipeline.assets.verify_store", lambda: {"files": {"weight": "a" * 64}}
    )
    calls = []

    def extract(self, rgb, mask):
        calls.append(1)
        return np.ones(384, np.float32)

    monkeypatch.setattr(NativeModels, "embedding", extract)
    models = CachedModels(V3Config(device="cpu", embedding_cache_entries=1))
    image, mask, _ = fixture_pair()
    first = models.embedding(image, mask)
    first[:] = 0
    assert models.embedding(image, mask).sum() > 0
    assert len(calls) == 1 and models.cache_hits == 1
    modified = image.copy()
    modified[100, 100] = 0
    models.embedding(modified, mask)
    models.embedding(image, mask)
    assert len(calls) == 3 and len(models.cache) == 1
    with pytest.raises(EPError):
        models.embedding(image, mask.ravel())


def test_cuda_oom_has_explicit_cpu_fallback(monkeypatch):
    import torch

    monkeypatch.setattr(torch.cuda, "empty_cache", lambda: None)
    pipeline = V3Pipeline(V3Config())

    def oom():
        raise torch.cuda.OutOfMemoryError("injected allocation failure")

    assert pipeline._gpu_or_cpu("appearance", oom, lambda: "cpu") == "cpu"
    assert pipeline.fallbacks == [{"operation": "appearance", "reason": "cuda_oom"}]


@pytest.mark.parametrize("changed", [False, True])
def test_mixed_resolution_comparison_does_not_invent_missing_reference_detail(changed):
    high = np.random.default_rng(816).integers(20, 230, (384, 384, 3), np.uint8)
    before = cv2.resize(high, (256, 256), interpolation=cv2.INTER_AREA)
    after = high.copy()
    if changed:
        after[150:190, 155:195] = 0
    before_mask = np.zeros((256, 256), bool)
    before_mask[24:-24, 24:-24] = True
    after_mask = cv2.resize(
        before_mask.astype(np.uint8), (384, 384), interpolation=cv2.INTER_NEAREST
    ).astype(bool)
    matrix = np.diag([1.5, 1.5, 1.0])
    config = V3Config(appearance_backend="opencv")
    pipeline = V3Pipeline(config)
    warped, overlap = pipeline._align_pair(before, before_mask, after_mask, matrix, config)
    difference, regions = pipeline._find_changes(warped, after, overlap, config)
    assert difference.shape == after_mask.shape
    assert not difference[~overlap].any()
    assert pipeline.comparison_frames[0]["analysis_dimensions"] == [256, 256]
    assert bool(regions) is changed
    if changed:
        assert any(
            x <= 155 and y <= 150 and x + w >= 195 and y + h >= 190 for x, y, w, h, _, _ in regions
        )
    else:
        assert difference.max() < 1e-5


@pytest.mark.parametrize("failure", ["model_oom", "models_unavailable", "model_integrity"])
def test_optional_model_failure_preserves_defensible_rootsift_evidence(failure):
    image, mask, _ = fixture_pair()
    config = V3Config(compare_matchers=True)

    def unavailable(*args):
        raise EPError(503, failure, "Injected optional matcher failure")

    matcher = HybridMatcher(config, learned=unavailable)
    pair, matrix = matcher(
        uuid4(),
        uuid4(),
        image,
        image,
        mask,
        mask,
        0.99,
        config,
        (local_features(image, mask), local_features(image, mask)),
    )
    assert matrix is not None and "rootsift" in pair.method
    assert matcher.records[0]["attempts"][1]["failure"] == failure


def test_gpu_geometry_oom_retries_same_verification_on_cpu(monkeypatch):
    import torch

    import ep_engine.v3.matching as matching

    original = matching.verify_correspondences
    monkeypatch.setattr(torch.cuda, "empty_cache", lambda: None)

    def estimate(src, dst, mask0, mask1, config):
        if config.geometry_backend == "kornia":
            raise torch.cuda.OutOfMemoryError("Injected geometry allocation failure")
        return original(src, dst, mask0, mask1, config)

    monkeypatch.setattr(matching, "verify_correspondences", estimate)
    _, mask, points = fixture_pair()
    matcher = HybridMatcher(V3Config(geometry_backend="kornia"))
    matrix, support, reason = matcher._verify(points, points, mask, mask, matcher.config)
    assert matrix is not None and support["inliers"] == len(points) and reason is None
    assert matcher.geometry_fallbacks == ["cuda_oom"]
