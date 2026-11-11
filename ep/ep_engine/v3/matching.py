"""Optional correspondences have no authority until independently verified geometrically."""

import hashlib
import sys
import time
from copy import deepcopy
from pickle import UnpicklingError

import cv2
import numpy as np
import psutil

from ep_engine.core.exceptions import EPError
from ep_engine.cv.contracts import Pair
from ep_engine.cv.geometry import geometric_support, local_features, validate_transform
from ep_engine.cv.numerics import bounded_cosine


def resource_snapshot():
    memory = psutil.Process().memory_info()
    result = {
        "process_rss_bytes": memory.rss,
        "process_peak_working_set_bytes": getattr(memory, "peak_wset", memory.rss),
    }
    torch = sys.modules.get("torch")
    if torch is not None and torch.cuda.is_available():
        result["current_cuda_allocated_bytes"] = torch.cuda.memory_allocated()
        result["cuda_high_water_bytes"] = torch.cuda.max_memory_allocated()
    return result


def rootsift_correspondences(features):
    (kp0, des0), (kp1, des1) = features
    if des0 is None or des1 is None or min(len(des0), len(des1)) < 8:
        return np.empty((0, 2), np.float32), np.empty((0, 2), np.float32)
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    reverse = {
        m.queryIdx: m.trainIdx
        for values in matcher.knnMatch(des1, des0, k=2)
        if len(values) == 2
        for m, n in [values]
        if m.distance < 0.75 * n.distance
    }
    matches = [
        m
        for values in matcher.knnMatch(des0, des1, k=2)
        if len(values) == 2
        for m, n in [values]
        if m.distance < 0.75 * n.distance and reverse.get(m.trainIdx) == m.queryIdx
    ]
    return (
        np.array([kp0[m.queryIdx].pt for m in matches], np.float32).reshape(-1, 2),
        np.array([kp1[m.trainIdx].pt for m in matches], np.float32).reshape(-1, 2),
    )


def filter_correspondences(src, dst, scores, before_mask, after_mask, minimum=0.5):
    src, dst, scores = np.asarray(src), np.asarray(dst), np.asarray(scores)
    if (
        src.ndim != 2
        or src.shape[1:] != (2,)
        or src.shape != dst.shape
        or scores.shape != (len(src),)
        or len(src) > 100_000
        or not all(np.isfinite(v).all() for v in (src, dst, scores))
    ):
        raise EPError(422, "invalid_correspondences", "Invalid learned correspondence output")
    valid = (scores >= minimum) & (scores <= 1)
    for points, mask in ((src, before_mask), (dst, after_mask)):
        h, w = mask.shape
        valid &= (points[:, 0] >= 0) & (points[:, 0] < w)
        valid &= (points[:, 1] >= 0) & (points[:, 1] < h)
        indices = np.clip(np.floor(points).astype(int), (0, 0), (w - 1, h - 1))
        valid &= mask[indices[:, 1], indices[:, 0]]
    # Duplicate endpoints cannot inflate geometric support. Confidence orders the cap.
    selected, used_src, used_dst = [], set(), set()
    for i in np.argsort(-scores, kind="stable"):
        if not valid[i]:
            continue
        a, b = tuple(np.round(src[i], 1)), tuple(np.round(dst[i], 1))
        if a in used_src or b in used_dst:
            continue
        selected.append(i)
        used_src.add(a)
        used_dst.add(b)
        if len(selected) >= 4096:
            break
    return src[selected].astype(np.float32), dst[selected].astype(np.float32)


def verify_correspondences(src, dst, before_mask, after_mask, config):
    """Both candidate models face identical bidirectional per-point and spatial tests."""
    src, dst = np.asarray(src, np.float32), np.asarray(dst, np.float32)
    if (
        src.shape != dst.shape
        or src.ndim != 2
        or src.shape[1:] != (2,)
        or any(not np.isfinite(points).all() for points in (src, dst))
        or len(src) > 4096
    ):
        raise EPError(422, "invalid_correspondences", "Invalid geometric inputs")
    if len(src) < config.min_inliers:
        return None, {}, "insufficient_correspondence"
    candidates = []
    if config.geometry_backend == "kornia":
        import torch
        from kornia.geometry.ransac import RANSAC

        if not torch.cuda.is_available():
            raise EPError(503, "cuda_unavailable", "GPU geometry requires CUDA")
        with torch.inference_mode(), torch.random.fork_rng(devices=[torch.cuda.current_device()]):
            torch.manual_seed(0)
            estimator = RANSAC("homography", inl_th=3.0, batch_size=256, max_iter=8)
            matrix, inliers = estimator(
                torch.from_numpy(src).to("cuda"), torch.from_numpy(dst).to("cuda")
            )
            candidates.append((matrix.cpu().numpy(), inliers.cpu().numpy(), "homography"))
    else:
        matrix, inliers = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
        candidates.append((matrix, inliers, "homography"))
    affine, inliers = cv2.estimateAffinePartial2D(
        src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0
    )
    if affine is not None:
        candidates.append((np.vstack((affine, [0, 0, 1])), inliers, "similarity"))
    accepted = []
    for matrix, inliers, model in candidates:
        try:
            matrix = validate_transform(matrix, before_mask.shape, after_mask.shape)
            if inliers is None or inliers.size != len(src):
                continue
            forward = cv2.perspectiveTransform(src[None], matrix)[0]
            reverse = cv2.perspectiveTransform(dst[None], np.linalg.inv(matrix))[0]
            scale = np.sqrt(after_mask.size / before_mask.size)
            valid = inliers.ravel().astype(bool)
            valid &= np.linalg.norm(forward - dst, axis=1) <= 3
            valid &= np.linalg.norm(reverse - src, axis=1) * scale <= 3
            support = geometric_support(src, dst, matrix, valid, before_mask, after_mask, config)
            if support:
                accepted.append((matrix, {**support, "geometry_model": model}))
        except (EPError, np.linalg.LinAlgError, cv2.error):
            continue
    if not accepted:
        return None, {}, "weak_geometric_support_or_view_change"
    # Prefer a lower-degree model when support is essentially equal.
    best = max(
        accepted,
        key=lambda row: (
            row[1]["inliers"],
            min(row[1]["source_coverage"], row[1]["target_coverage"]),
            row[1]["geometry_model"] == "similarity",
            -row[1]["symmetric_reprojection_error"],
        ),
    )
    return *best, None


class LoFTRMatcher:
    def __init__(self, config):
        self.config, self.model = config, None
        self.load_seconds = 0.0

    def close(self):
        self.model = None

    def _load(self):
        if self.model is not None:
            return
        import torch
        from kornia.feature import LoFTR

        if not torch.cuda.is_available():
            raise EPError(503, "cuda_unavailable", "Learned matching requires CUDA")
        if torch.cuda.mem_get_info()[0] < 2 * 1024**3:
            raise EPError(503, "memory_reserve", "Insufficient free VRAM for optional matcher")
        if psutil.virtual_memory().available < 1.5 * 1024**3:
            raise EPError(503, "memory_reserve", "Insufficient free host RAM for optional matcher")
        path = self.config.checkpoint
        if not path.is_file():
            raise EPError(503, "models_unavailable", "Optional checkpoint is unavailable")
        if path.stat().st_size > 128_000_000:
            raise EPError(409, "model_integrity", "Optional checkpoint exceeds memory budget")
        if hashlib.sha256(path.read_bytes()).hexdigest() != self.config.checkpoint_sha256:
            raise EPError(409, "model_integrity", "Optional checkpoint digest mismatch")
        started = time.perf_counter()
        # pretrained=None is essential: request handling must never download weights.
        model = LoFTR(pretrained=None)
        try:
            state = torch.load(path, map_location="cpu", weights_only=True)
        except (OSError, ValueError, UnpicklingError) as exc:
            raise EPError(
                409, "unsafe_checkpoint", "Optional checkpoint could not be loaded safely"
            ) from exc
        if not isinstance(state, dict):
            raise EPError(409, "unsafe_checkpoint", "Optional checkpoint must contain tensor state")
        state = state.get("state_dict", state)
        if not isinstance(state, dict) or any(
            not isinstance(v, torch.Tensor) or not torch.isfinite(v).all() for v in state.values()
        ):
            raise EPError(
                409, "unsafe_checkpoint", "Optional checkpoint must contain finite tensors"
            )
        try:
            model.load_state_dict(state, strict=True)
        except RuntimeError as exc:
            raise EPError(
                409, "unsafe_checkpoint", "Optional checkpoint tensor keys or shapes differ"
            ) from exc
        self.model = model.eval().requires_grad_(False).to("cuda")
        torch.cuda.synchronize()
        self.load_seconds = time.perf_counter() - started

    def __call__(self, before, after, before_mask, after_mask):
        import torch

        try:
            self._load()
            images, scales = [], []
            for rgb in (before, after):
                h, w = rgb.shape[:2]
                scale = min(1.0, self.config.learned_max_side / max(h, w))
                # LoFTR requires dimensions divisible by eight. Track both scales exactly.
                nh, nw = max(8, int(h * scale) // 8 * 8), max(8, int(w * scale) // 8 * 8)
                gray = cv2.resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), (nw, nh))
                images.append(torch.from_numpy(gray.copy()).float()[None, None].to("cuda") / 255)
                scales.append(np.array([w / nw, h / nh], np.float32))
            with torch.inference_mode():
                result = self.model({"image0": images[0], "image1": images[1]})
            return filter_correspondences(
                result["keypoints0"].cpu().numpy() * scales[0],
                result["keypoints1"].cpu().numpy() * scales[1],
                result["confidence"].cpu().numpy(),
                before_mask,
                after_mask,
                self.config.learned_confidence,
            )
        except torch.cuda.OutOfMemoryError as exc:
            self.close()
            torch.cuda.empty_cache()
            raise EPError(503, "model_oom", "Optional matcher exceeded its VRAM budget") from exc


class HybridMatcher:
    def __init__(self, config, learned=None):
        self.config = config
        self.learned = learned or (
            LoFTRMatcher(config) if config.learned_matcher == "loftr" else None
        )
        self.records = []
        self.correspondences = {}
        self.geometry_fallbacks = []

    def close(self):
        if self.learned is not None and hasattr(self.learned, "close"):
            self.learned.close()

    def _verify(self, src, dst, mask0, mask1, config):
        try:
            return verify_correspondences(src, dst, mask0, mask1, config)
        except ImportError:
            reason = "optional_dependency_unavailable"
        except EPError as exc:
            if exc.code != "cuda_unavailable":
                raise
            reason = exc.code
        except RuntimeError as exc:
            import torch

            if not isinstance(exc, torch.cuda.OutOfMemoryError):
                raise
            self.close()
            torch.cuda.empty_cache()
            reason = "cuda_oom"
        self.geometry_fallbacks.append(reason)
        cpu_config = config.model_copy(update={"geometry_backend": "opencv"})
        return verify_correspondences(src, dst, mask0, mask1, cpu_config)

    def __call__(self, *args):
        before_id, after_id, before, after, mask0, mask1, similarity, config, *_ = args
        similarity = bounded_cosine(similarity)
        started = time.perf_counter()
        root = Pair(
            before_id=before_id,
            after_id=after_id,
            cosine_similarity=similarity,
            method="dinov2_rootsift_bidirectional_v3",
        )
        matrix = None
        if similarity < config.min_similarity:
            root.reasons.append("embedding_inconsistent")
        else:
            root.local_matching_evaluated = True
            features = (
                args[8]
                if len(args) > 8
                else (local_features(before, mask0), local_features(after, mask1))
            )
            src, dst = rootsift_correspondences(features)
            src, dst = filter_correspondences(src, dst, np.ones(len(src)), mask0, mask1)
            fallback_count = len(self.geometry_fallbacks)
            matrix, support, reason = self._verify(src, dst, mask0, mask1, config)
            if len(self.geometry_fallbacks) > fallback_count:
                root.reasons.append("gpu_geometry_unavailable_cpu_verification")
            root.method = "dinov2_rootsift_bidirectional_v3"
            root.matches = len(src)
            if matrix is not None:
                for key, value in support.items():
                    setattr(root, key, value)
                root.homography, root.identity = matrix.tolist(), "consistent_visual_evidence"
                self.correspondences[(before_id, after_id)] = (src, dst)
                root.reasons = [
                    r for r in root.reasons if r == "gpu_geometry_unavailable_cpu_verification"
                ]
            else:
                root.homography, root.identity = None, "uncertain"
                root.inliers, root.inlier_ratio = 0, 0
                root.reasons.append(reason)
        records = [
            {
                "matcher": "rootsift",
                "seconds": time.perf_counter() - started,
                "valid": matrix is not None,
                "resources": resource_snapshot(),
                **root.model_dump(mode="json"),
            }
        ]
        best = root
        weak = (
            matrix is None
            or root.inlier_ratio < 0.65
            or min(root.source_coverage, root.target_coverage) < 0.10
        )
        if (
            self.learned is not None
            and similarity >= config.min_similarity
            and (weak or self.config.compare_matchers)
        ):
            started = time.perf_counter()
            candidate = Pair(
                before_id=before_id,
                after_id=after_id,
                cosine_similarity=similarity,
                method="dinov2_loftr_verified_v3",
                local_matching_evaluated=True,
            )
            try:
                src, dst = self.learned(before, after, mask0, mask1)
                # Also validate injected adapters; they do not bypass mask/duplicate checks.
                src, dst = filter_correspondences(src, dst, np.ones(len(src)), mask0, mask1)
                candidate.matches = len(src)
                alternative, support, reason = self._verify(src, dst, mask0, mask1, config)
                if alternative is None:
                    candidate.reasons.append(reason)
                else:
                    for key, value in support.items():
                        setattr(candidate, key, value)
                    candidate.homography = alternative.tolist()
                    candidate.identity = "consistent_visual_evidence"

                    def rank(p):
                        # Dense learned matches are correlated. Count alone cannot
                        # outweigh a less precise warp or marginal coverage gain.
                        error = p.symmetric_reprojection_error or 0
                        return (
                            min(p.source_coverage, p.target_coverage)
                            * p.inlier_ratio
                            / (1 + error),
                            min(p.inliers, 200),
                            -error,
                        )

                    if matrix is None or rank(candidate) > rank(best):
                        best, matrix = candidate, alternative
                        self.correspondences[(before_id, after_id)] = (src, dst)
                records.append(
                    {
                        "matcher": "loftr",
                        "seconds": time.perf_counter() - started,
                        "valid": alternative is not None,
                        "model_load_seconds": getattr(self.learned, "load_seconds", 0),
                        "resources": resource_snapshot(),
                        **candidate.model_dump(mode="json"),
                    }
                )
            except (EPError, ImportError) as exc:
                records.append(
                    {
                        "matcher": "loftr",
                        "valid": False,
                        "seconds": time.perf_counter() - started,
                        "failure": exc.code
                        if isinstance(exc, EPError)
                        else "optional_dependency_unavailable",
                    }
                )
        self.records.append(
            {
                "before_id": str(before_id),
                "after_id": str(after_id),
                "selected": best.method,
                "attempts": deepcopy(records),
            }
        )
        return best, matrix
