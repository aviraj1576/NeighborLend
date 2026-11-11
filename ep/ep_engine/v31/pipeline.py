"""Retain validated geometry; abstain on unresolved movable-instance assignments."""

import time

import cv2
import numpy as np

from ep_engine.core.exceptions import EPError
from ep_engine.cv.contracts import Pair
from ep_engine.v3.matching import filter_correspondences, resource_snapshot
from ep_engine.v3.pipeline import V3Pipeline
from ep_engine.v31.matching import cropped_matches, local_surfaces
from ep_engine.v31.models import InspectionModels


def mask_components(mask):
    # Thin segmentation bridges can connect two independently movable items.
    # Splitting them is an ambiguity signal, never an automatic instance assignment.
    scales = {5, max(5, 2 * int(min(mask.shape) * 0.05) + 1)}
    maximum = 0
    for size in scales:
        core = cv2.erode(mask.astype(np.uint8), np.ones((size, size), np.uint8))
        count, _, stats, _ = cv2.connectedComponentsWithStats(core)
        maximum = max(
            maximum,
            sum(
                stats[index, cv2.CC_STAT_AREA] >= max(64, 0.12 * mask.sum())
                for index in range(1, count)
            ),
        )
    return maximum


class InspectionPipeline(V3Pipeline):
    def __init__(self, config, models=None, learned=None, instance_ids=None):
        super().__init__(config, models, learned)
        self.instance_ids = instance_ids or {}
        self._match_pair = self._instance_match
        self.local_surfaces = []

    def run(self, *args, **kwargs):
        self.local_surfaces.clear()
        result = super().run(*args, **kwargs)
        result.models["algorithm_revision"] = "ep-v3.1-scoped-refinement-1"
        return result

    def _segment(self):
        if self.models is None and any(
            row.target is not None and self.quality[row.id].status == "usable"
            for row in self.inputs
        ):
            self.models = InspectionModels(self.config)
        super()._segment()

    def _sampling_scale(self, matrix, mask):
        """Conservative Jacobian bound over the object's bounding rectangle.

        Each projective derivative numerator is linear; its absolute maximum
        and the denominator minimum occur at rectangle corners. The spectral
        norm of elementwise bounds upper-bounds every local magnification.
        No sparse-mask sampling is claimed to prove a continuous maximum.
        """
        ys, xs = np.where(mask)
        if not len(xs):
            raise EPError(422, "insufficient_overlap", "Empty supported object region")
        points = np.array([[x, y, 1.0] for x in (xs.min(), xs.max()) for y in (ys.min(), ys.max())])
        projected = points @ matrix.T
        denominators = projected[:, 2]
        if not np.isfinite(projected).all() or denominators.min() <= 1e-8:
            raise EPError(422, "unstable_geometry", "Invalid object sampling geometry")
        numerators = np.array(
            [matrix[:2, :2] * p[2] - np.outer(p[:2], matrix[2, :2]) for p in projected]
        )
        bound = np.max(np.abs(numerators), axis=0) / denominators.min() ** 2
        return 1 / max(1.0, float(np.linalg.norm(bound, ord=2)))

    def _instance_match(self, *args):
        before, after, image0, image1, mask0, mask1, similarity, *_ = args
        first, second = self.instance_ids.get(before), self.instance_ids.get(after)
        reason = None
        if (first is not None or second is not None) and first != second:
            reason = "ambiguous_instance_assignment"
        elif (mask_components(mask0) > 1 or mask_components(mask1) > 1) and not (
            image0.shape == image1.shape and np.array_equal(image0, image1)
        ):
            reason = "multiple_movable_instances_require_separate_targets"
        if reason:
            return Pair(
                before_id=before, after_id=after, cosine_similarity=similarity, reasons=[reason]
            ), None
        pair, matrix = self.hybrid(*args)
        if (
            matrix is not None
            or similarity < self.config.min_similarity
            or self.hybrid.learned is None
        ):
            return pair, matrix
        # A bounded real-image experiment justified only the half-turn fallback.
        # Keep all geometry/overlap gates and original output coordinates intact.
        started = time.perf_counter()
        record = {"matcher": "loftr_rot180", "valid": False}
        try:
            src, rotated = self.hybrid.learned(
                image0, np.rot90(image1, 2).copy(), mask0, np.rot90(mask1, 2).copy()
            )
            dst = rotated.copy()
            dst[:, 0] = image1.shape[1] - 1 - rotated[:, 0]
            dst[:, 1] = image1.shape[0] - 1 - rotated[:, 1]
            src, dst = filter_correspondences(src, dst, np.ones(len(src)), mask0, mask1)
            alternative, support, reason = self.hybrid._verify(src, dst, mask0, mask1, self.config)
            if alternative is not None:
                candidate = Pair(
                    before_id=before,
                    after_id=after,
                    cosine_similarity=pair.cosine_similarity,
                    matches=len(src),
                    local_matching_evaluated=True,
                    method="dinov2_loftr_rot180_verified_v31",
                    identity="consistent_visual_evidence",
                    homography=alternative.tolist(),
                    **support,
                )
                pair, matrix = candidate, alternative
                self.hybrid.correspondences[(before, after)] = (src, dst)
                record.update(valid=True, **candidate.model_dump(mode="json"))
            else:
                record["rejection"] = reason
        except (EPError, ImportError) as exc:
            record["failure"] = (
                exc.code if isinstance(exc, EPError) else "optional_dependency_unavailable"
            )
        record["seconds"] = time.perf_counter() - started
        record["resources"] = resource_snapshot()
        self.hybrid.records[-1]["attempts"].append(record)
        self.hybrid.records[-1]["selected"] = pair.method
        if matrix is None:
            pair, matrix = self._crop_match(args, pair)
        return pair, matrix

    def _crop_match(self, args, pair):
        before, after, image0, image1, mask0, mask1, similarity, *_ = args
        local = []
        for turns in (0, 1, 2, 3):
            started = time.perf_counter()
            record = {"matcher": "loftr_object_crop", "quarter_turns": turns, "valid": False}
            try:
                src, dst = cropped_matches(self.hybrid.learned, image0, image1, mask0, mask1, turns)
                alternative, support, reason = self.hybrid._verify(
                    src, dst, mask0, mask1, self.config
                )
                record.update(matches=len(src), rejection=reason)
                if alternative is not None:
                    pair = Pair(
                        before_id=before,
                        after_id=after,
                        cosine_similarity=similarity,
                        matches=len(src),
                        local_matching_evaluated=True,
                        method=f"dinov2_loftr_object_crop_rot{turns * 90}_v31",
                        identity="consistent_visual_evidence",
                        homography=alternative.tolist(),
                        **support,
                    )
                    self.hybrid.correspondences[(before, after)] = (src, dst)
                    record.update(valid=True, **support)
                elif len(src) >= 2 * self.config.min_inliers:
                    local.extend(
                        local_surfaces(
                            src, dst, image0, mask0, mask1, self.config, self.hybrid._verify
                        )
                    )
            except (EPError, ImportError) as error:
                record["failure"] = (
                    error.code if isinstance(error, EPError) else "optional_dependency_unavailable"
                )
                alternative = None
            record["seconds"] = time.perf_counter() - started
            self.hybrid.records[-1]["attempts"].append(record)
            if alternative is not None:
                self.hybrid.records[-1]["selected"] = pair.method
                return pair, alternative
            if "failure" in record:
                break  # A missing dependency/OOM is not a reason for more GPU attempts.
        if local and len(self.local_surfaces) < 4:
            best = max(local, key=lambda row: int(row["overlap"].sum()))
            self.local_surfaces.append(dict(before_id=before, after_id=after, **best))
            pair.reasons.append("local_surface_evidence_only_global_geometry_unverified")
        return pair, None
