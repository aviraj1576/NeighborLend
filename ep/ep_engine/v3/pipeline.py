import hashlib
from collections import OrderedDict
from copy import deepcopy

import cv2
import numpy as np

from ep_engine.core.exceptions import EPError
from ep_engine.cv import assets
from ep_engine.cv.contracts import CVPackage
from ep_engine.cv.models import NativeModels, check_embedding, check_mask
from ep_engine.cv.pipeline import CVPipeline
from ep_engine.v3.gpu import align_cuda, appearance_cuda
from ep_engine.v3.matching import HybridMatcher


class CachedModels(NativeModels):
    def __init__(self, config):
        super().__init__(config.device)
        self.limit = config.embedding_cache_entries
        self.cache = OrderedDict()
        self.cache_hits = 0
        # Bind cached output to verified weight bytes and preprocessing, not filenames.
        self.receipt = assets.verify_store()["files"]

    def embedding(self, rgb, mask):
        check_mask(mask, rgb.shape[:2])
        key = hashlib.sha256()
        key.update(b"full_object_letterbox_rot4-fp32-v3")
        key.update(str(sorted(self.receipt.items())).encode())
        key.update(str((rgb.shape, rgb.dtype, mask.shape, mask.dtype, self.device)).encode())
        key.update(rgb.tobytes())
        key.update(mask.tobytes())
        digest = key.digest()
        if digest in self.cache:
            self.cache_hits += 1
            self.cache.move_to_end(digest)
            return self.cache[digest].copy()
        result = check_embedding(super().embedding(rgb, mask))
        if self.limit:
            self.cache[digest] = result.copy()
            while len(self.cache) > self.limit:
                self.cache.popitem(last=False)
        return result

    def metrics(self):
        return {
            **super().metrics(),
            "embedding_cache_hits": self.cache_hits,
            "embedding_cache_entries": len(self.cache),
        }


class V3Pipeline(CVPipeline):
    """Opt-in engine; inherited v2 serialization and safety gates remain intact."""

    def __init__(self, config, models=None, learned=None):
        super().__init__(config, models)
        self.hybrid = HybridMatcher(config, learned)
        self._match_pair = self.hybrid
        self.fallbacks = []
        self.comparison_inputs = {}
        self.comparison_frames = []

    def _segment(self):
        # Lazy load preserves cheap quality-gate rejection without loading CUDA/models.
        if self.models is None and any(
            row.target is not None and self.quality[row.id].status == "usable"
            for row in self.inputs
        ):
            self.models = CachedModels(self.config)
        super()._segment()

    def _features(self):
        super()._features()
        if self.models is not None:
            self.models.close()  # Free DINO before optional learned matcher/warping.

    def _gpu_or_cpu(self, operation, gpu, cpu, *args):
        try:
            return gpu(*args)
        except ImportError:
            self.fallbacks.append(
                {"operation": operation, "reason": "optional_dependency_unavailable"}
            )
        except EPError as exc:
            if exc.code != "cuda_unavailable":
                raise
            self.fallbacks.append({"operation": operation, "reason": exc.code})
        except RuntimeError as exc:
            import torch

            if not isinstance(exc, torch.cuda.OutOfMemoryError):
                raise
            self.hybrid.close()
            torch.cuda.empty_cache()
            self.fallbacks.append({"operation": operation, "reason": "cuda_oom"})
        return cpu(*args)

    def _align_pair(self, *args):
        if self.config.alignment_backend == "cuda":
            result = self._gpu_or_cpu("alignment", align_cuda, super()._align_pair, *args)
        else:
            result = super()._align_pair(*args)
        self.comparison_inputs[id(result[0])] = args
        return result

    @staticmethod
    def _comparison_scale(matrix, shape):
        # Bound local magnification over the reference frame. Upsampling a reference
        # cannot supply fine detail present only in a higher-resolution return image.
        h, w = shape
        maximum = 1.0
        for x in (0, w / 2, w - 1):
            for y in (0, h / 2, h - 1):
                p = matrix @ np.array([x, y, 1.0])
                if not np.isfinite(p).all() or p[2] <= 1e-8:
                    raise EPError(422, "unstable_geometry", "Invalid local sampling geometry")
                jacobian = (matrix[:2, :2] * p[2] - np.outer(p[:2], matrix[2, :2])) / p[2] ** 2
                maximum = max(maximum, float(np.linalg.svd(jacobian, compute_uv=False)[0]))
        return 1 / maximum

    def _find_changes(self, *args):
        warped, after, overlap, config = args
        original = self.comparison_inputs.get(id(warped))
        if original is not None:
            before, before_mask, after_mask, matrix, _ = original
            scale = self._sampling_scale(matrix, before_mask)
            # Ignore subpixel resize roundoff; otherwise compare at the available
            # reference sampling density, preserving output boxes in the target frame.
            if scale < 1 / 1.05:
                h, w = overlap.shape
                nw, nh = max(8, round(w * scale)), max(8, round(h * scale))
                resize = np.diag([nw / w, nh / h, 1.0])
                coarse_mask = cv2.resize(
                    after_mask.astype(np.uint8), (nw, nh), interpolation=cv2.INTER_NEAREST
                ).astype(bool)
                coarse_before, coarse_overlap = super()._align_pair(
                    before, before_mask, coarse_mask, resize @ matrix, config
                )
                coarse_overlap &= (
                    cv2.resize(overlap.astype(np.float32), (nw, nh), interpolation=cv2.INTER_AREA)
                    > 0.999
                )
                coarse_after = cv2.resize(after, (nw, nh), interpolation=cv2.INTER_AREA)
                difference, regions = self._appearance(
                    coarse_before, coarse_after, coarse_overlap, config
                )
                restored = cv2.resize(difference, (w, h), interpolation=cv2.INTER_LINEAR)
                restored[~overlap] = 0
                converted = []
                for x, y, width, height, area, score in regions:
                    x1, y1 = int(np.floor(x * w / nw)), int(np.floor(y * h / nh))
                    x2 = min(w, int(np.ceil((x + width) * w / nw)))
                    y2 = min(h, int(np.ceil((y + height) * h / nh)))
                    converted.append(
                        (x1, y1, x2 - x1, y2 - y1, round(area * w * h / (nw * nh)), score)
                    )
                self.comparison_frames.append(
                    {
                        "target_dimensions": [w, h],
                        "analysis_dimensions": [nw, nh],
                        "reason": "reference_sampling_density",
                    }
                )
                return restored, converted
        return self._appearance(*args)

    def _sampling_scale(self, matrix, mask):
        return self._comparison_scale(matrix, mask.shape)

    def _appearance(self, *args):
        if self.config.appearance_backend == "cuda" and self.config.device != "cpu":
            return self._gpu_or_cpu("appearance", appearance_cuda, super()._find_changes, *args)
        return super()._find_changes(*args)

    def _match_visualization(self, before, after, matrix):
        points = self.hybrid.correspondences.get((before, after))
        if points is None:
            return super()._match_visualization(before, after, matrix)
        src, dst = points
        predicted = cv2.perspectiveTransform(src[None], matrix)[0]
        indices = np.flatnonzero(np.linalg.norm(predicted - dst, axis=1) <= 3)[:40]
        keypoints = [
            [cv2.KeyPoint(float(p[0]), float(p[1]), 1) for p in ps[indices]] for ps in (src, dst)
        ]
        return cv2.drawMatches(
            self.images[before],
            keypoints[0],
            self.images[after],
            keypoints[1],
            [cv2.DMatch(i, i, 0) for i in range(len(indices))],
            None,
            flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
        )

    def run(self, *args, **kwargs):
        self.hybrid.records.clear()
        self.hybrid.correspondences.clear()
        self.hybrid.geometry_fallbacks.clear()
        self.fallbacks.clear()
        self.comparison_inputs.clear()
        self.comparison_frames.clear()
        try:
            result = super().run(*args, **kwargs)
            if self.comparison_frames:
                result.limitations.append(
                    "Appearance comparison is limited to reference sampling density; "
                    "finer detail present only in the return image is unassessable"
                )
            result.models["algorithm_revision"] = "ep-v3.1-advisory"
            result.metrics["v3"] = {
                "config": self.config.model_dump(mode="json"),
                "matching": deepcopy(self.hybrid.records),
                "fallbacks": deepcopy(self.fallbacks),
                "geometry_fallbacks": self.hybrid.geometry_fallbacks.copy(),
                "comparison_frames": deepcopy(self.comparison_frames),
                "payment_action": "none",
            }
            # Validate values assigned during incremental stages and nested telemetry.
            return CVPackage.model_validate(result.model_dump())
        finally:
            self.hybrid.close()
