import time
from dataclasses import dataclass
from functools import partial
from uuid import UUID, uuid4

import cv2
import numpy as np

from ep_engine.core.exceptions import EPError
from ep_engine.cv.artifacts import ArtifactWriter
from ep_engine.cv.changes import boundary_regions, find_changes
from ep_engine.cv.contracts import BoundaryChange, Candidate, CVPackage, Segmentation
from ep_engine.cv.geometry import align_pair, local_features, match_pair
from ep_engine.cv.models import NativeModels, check_embedding, check_mask
from ep_engine.cv.numerics import bounded_cosine
from ep_engine.cv.quality import assess_quality
from ep_engine.cv.targeting import validate_target_mask
from ep_engine.pipeline.interfaces import STAGE_ORDER, PipelineContext, StageResult
from ep_engine.pipeline.orchestrator import Orchestrator
from ep_engine.schemas.models import Box


@dataclass
class InputImage:
    id: UUID
    stage: str
    rgb: np.ndarray
    sha256: str
    target: Box | None
    original_size: tuple[int, int] | None = None
    view: str | None = None
    original_rgb: np.ndarray | None = None


def normalized_box(x, y, width, height, shape):
    h, w = shape
    return Box(
        x1=max(0, x / w), y1=max(0, y / h), x2=min(1, (x + width) / w), y2=min(1, (y + height) / h)
    )


def source_box(after_box, matrix, before_shape):
    x, y, width, height = after_box
    points = np.float32([[[x, y], [x + width, y], [x + width, y + height], [x, y + height]]])
    transformed = cv2.perspectiveTransform(points, np.linalg.inv(matrix))[0]
    low = transformed.min(axis=0)
    high = transformed.max(axis=0)
    return normalized_box(
        float(low[0]), float(low[1]), float(high[0] - low[0]), float(high[1] - low[1]), before_shape
    )


class CVPipeline:
    # Standalone experimental engines can replace operations without changing the v2 defaults.
    _match_pair = staticmethod(match_pair)
    _align_pair = staticmethod(align_pair)
    _find_changes = staticmethod(find_changes)

    def __init__(self, config, models=None):
        self.config = config
        self.models = models

    def run(self, inspection_id, inputs: list[InputImage], artifact_dir):
        if not 2 <= len(inputs) <= self.config.max_images or len({row.id for row in inputs}) != len(
            inputs
        ):
            raise EPError(413, "processing_limit", "Invalid evidence count")
        if {row.stage for row in inputs} != {"before", "after"}:
            raise EPError(422, "invalid_evidence", "Before and after evidence are required")
        if any(
            row.view is not None and (not isinstance(row.view, str) or len(row.view) > 128)
            for row in inputs
        ):
            raise EPError(422, "invalid_evidence", "Invalid view label")
        cv2.setNumThreads(1)
        cv2.setRNGSeed(0)
        self.inputs = inputs
        self.writer = ArtifactWriter(artifact_dir, [row.id for row in inputs])
        self.images, self.quality, self.masks, self.segmentation, self.embeddings = (
            {},
            {},
            {},
            {},
            {},
        )
        self.features, self.pairs, self.geometries, self.aligned, self.candidates = (
            {},
            [],
            {},
            {},
            [],
        )
        self.stage_seconds = {}
        self.image_seconds = {}
        self.boundary_changes = []
        self.boundary_limitations = []
        self.candidates_truncated = False
        self.dimensions = {
            row.id: row.original_size or (row.rgb.shape[1], row.rgb.shape[0]) for row in inputs
        }
        started = time.perf_counter()
        stages = {
            name: self._stage(name, callback)
            for name, callback in zip(
                STAGE_ORDER[:6],
                (
                    self._quality,
                    self._segment,
                    self._features,
                    self._match,
                    self._align,
                    self._changes,
                ),
                strict=True,
            )
        }
        context = PipelineContext(
            inspection_id=inspection_id,
            reference_ids=[r.id for r in inputs if r.stage == "before"],
            return_ids=[r.id for r in inputs if r.stage == "after"],
        )
        try:
            Orchestrator(stages).run_cv(context)
            matched = {
                key
                for pair in self.pairs
                if pair.status == "comparable"
                for key in (pair.before_id, pair.after_id)
            }
            unmatched = [row.id for row in inputs if row.id not in matched]
            outcome = (
                "inconclusive"
                if not matched
                else "partially_comparable"
                if unmatched
                else "comparable"
            )
            metrics = self.models.metrics() if self.models is not None else {"device": "not_loaded"}
            return CVPackage(
                inspection_id=inspection_id,
                outcome=outcome,
                source_ids=[r.id for r in inputs],
                source_hashes={r.id: r.sha256 for r in inputs},
                source_dimensions=self.dimensions,
                processing_dimensions={
                    key: (value.shape[1], value.shape[0]) for key, value in self.images.items()
                },
                quality=list(self.quality.values()),
                segmentation=list(self.segmentation.values()),
                pairs=self.pairs,
                candidates=self.candidates,
                boundary_changes=self.boundary_changes,
                artifacts=self.writer.records,
                unmatched_ids=unmatched,
                models={
                    "segmentation": "EfficientSAM-Ti@d525f622e6f640acf5a0fc37c7ca1f243da5bde0",
                    "embedding": "DINOv2-S14@7764ea0f912e53c92e82eb78a2a1631e92725fc8",
                    "adapter": type(self.models).__name__,
                    "algorithm_revision": "ep-cv-2.1-advisory",
                    "embedding_preprocessing": "full_object_letterbox_rot4",
                    "local_features": "clahe_rootsift_precise_pyramid",
                    "boundary_validation": "silhouette_and_photometric_support",
                },
                thresholds=self.config,
                metrics={
                    **metrics,
                    "stage_seconds": self.stage_seconds,
                    "total_seconds": time.perf_counter() - started,
                    "per_image_seconds": self.image_seconds,
                    "candidates_truncated": int(self.candidates_truncated),
                },
                limitations=[
                    "Visual changes are not confirmed damage",
                    "Physical object identity is not proven by visual similarity",
                    "Homography supports locally planar appearance only; "
                    "3D, reflective and occluded regions may be unassessable",
                    "Thresholds are experimental and require independent real-data evaluation",
                    "No inference about unseen reference surfaces",
                    "Shape-valid masks are not proof of correct object targeting",
                    "No candidates does not establish an unchanged object or functional condition",
                    *(
                        [
                            "Appearance candidates exceeded the artifact budget; "
                            "comparison is incomplete"
                        ]
                        if self.candidates_truncated
                        else []
                    ),
                    *dict.fromkeys(self.boundary_limitations),
                ],
            )
        finally:
            if self.models is not None:
                self.models.close()

    def _image_timed(self, key, operation, callback):
        started = time.perf_counter()
        try:
            return callback()
        finally:
            self.image_seconds.setdefault(str(key), {})[operation] = time.perf_counter() - started

    def _stage(self, name, callback):
        def execute(context):
            started = time.perf_counter()
            callback()
            self.stage_seconds[name] = time.perf_counter() - started
            return StageResult(
                stage=name,
                evidence_ids=[row.id for row in self.inputs],
                artifact_keys=[row.id for row in self.writer.records],
            )

        return execute

    def _quality(self):
        for row in self.inputs:
            image = row.rgb
            if (
                image.dtype != np.uint8
                or image.ndim != 3
                or image.shape[2] != 3
                or image.shape[0] * image.shape[1] > 16_000_000
            ):
                raise EPError(413, "processing_limit", "Invalid source image")
            scale = min(1, self.config.max_side / max(image.shape[:2]))
            if scale < 1:
                image = cv2.resize(
                    image,
                    (max(1, round(image.shape[1] * scale)), max(1, round(image.shape[0] * scale))),
                    interpolation=cv2.INTER_AREA,
                )
            self.images[row.id] = image
            self.quality[row.id] = self._image_timed(
                row.id, "quality", partial(assess_quality, row.id, image, self.config)
            )

    def _segment(self):
        for row in self.inputs:
            record = Segmentation(evidence_id=row.id, status="inconclusive")
            self.segmentation[row.id] = record
            if row.target is None or self.quality[row.id].status != "usable":
                record.limitations = [
                    "explicit_target_required"
                    if row.target is None
                    else "image_quality_insufficient"
                ]
                continue
            if self.models is None:
                self.models = NativeModels(self.config.device)
            image = self.images[row.id]
            try:
                mask = check_mask(
                    self._image_timed(
                        row.id,
                        "segmentation",
                        partial(
                            self.models.segment,
                            image,
                            (row.target.x1, row.target.y1, row.target.x2, row.target.y2),
                        ),
                    ),
                    image.shape[:2],
                )
                record.target_support = validate_target_mask(
                    mask, (row.target.x1, row.target.y1, row.target.x2, row.target.y2)
                )
            except EPError as exc:
                if exc.code != "invalid_mask":
                    raise
                record.limitations = [
                    "segmentation_ambiguous_or_empty",
                    "Select a tight object target; avoid background, hands and partial objects",
                ]
                continue
            self.quality[row.id] = assess_quality(row.id, image, self.config, mask)
            if self.quality[row.id].status != "usable":
                record.limitations = ["object_quality_insufficient"]
                continue
            self.masks[row.id] = mask
            ys, xs = np.where(mask)
            record.status, record.area_fraction = "segmented", float(mask.mean())
            record.box = normalized_box(
                int(xs.min()),
                int(ys.min()),
                int(xs.max() - xs.min() + 1),
                int(ys.max() - ys.min() + 1),
                mask.shape,
            )
            record.mask_id = self.writer.save("object_mask", mask.astype(np.uint8) * 255, [row.id])
            self.writer.save(
                "object_crop", image[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1], [row.id]
            )

    def _features(self):
        for key, mask in self.masks.items():
            self.embeddings[key] = check_embedding(
                self._image_timed(
                    key, "embedding", partial(self.models.embedding, self.images[key], mask)
                )
            )
            self.features[key] = self._image_timed(
                key, "local_features", partial(local_features, self.images[key], mask)
            )

    def _match(self):
        combinations = [
            (bounded_cosine(self.embeddings[b.id] @ self.embeddings[a.id]), b.id, a.id)
            for b in self.inputs
            if b.stage == "before" and b.id in self.embeddings
            for a in self.inputs
            if a.stage == "after"
            and a.id in self.embeddings
            and (not b.view or not a.view or b.view.strip().casefold() == a.view.strip().casefold())
        ]
        for similarity, before, after in sorted(combinations, key=lambda row: row[0], reverse=True)[
            : self.config.max_pairs
        ]:
            pair, matrix = self._match_pair(
                before,
                after,
                self.images[before],
                self.images[after],
                self.masks[before],
                self.masks[after],
                similarity,
                self.config,
                (self.features[before], self.features[after]),
            )
            self.pairs.append(pair)
            if matrix is not None:
                self.geometries[(before, after)] = matrix

    def _align(self):
        selected = set()
        for pair in sorted(
            self.pairs, key=lambda row: (row.inliers, row.cosine_similarity), reverse=True
        ):
            before, after = pair.before_id, pair.after_id
            matrix = self.geometries.get((before, after))
            if matrix is None:
                continue
            if after in selected:
                pair.reasons.append("alternate_pair_not_selected")
                continue
            try:
                pair.alignment_status = "rejected"
                warped, overlap = self._align_pair(
                    self.images[before], self.masks[before], self.masks[after], matrix, self.config
                )
            except EPError as exc:
                if exc.code not in {
                    "unstable_geometry",
                    "insufficient_overlap",
                    "ambiguous_instances",
                }:
                    raise
                pair.reasons.append(exc.code)
                continue
            selected.add(after)
            pair.status = "comparable"
            pair.alignment_status = "aligned"
            pair.overlap_fraction = float(overlap.sum() / max(1, self.masks[after].sum()))
            self.aligned[(before, after)] = (warped, overlap)
            pair.overlap_id = self.writer.save(
                "valid_overlap", overlap.astype(np.uint8) * 255, [before, after]
            )
            visualization = self._match_visualization(before, after, matrix)
            self.writer.save("feature_matches", visualization, [before, after])
            self.writer.save("aligned_before", warped, [before, after])
            self.writer.save(
                "alignment_overlay",
                cv2.addWeighted(warped, 0.5, self.images[after], 0.5, 0),
                [before, after],
            )

    def _match_visualization(self, before, after, matrix):
        kp1, des1 = self.features[before]
        kp2, des2 = self.features[after]
        matches = cv2.BFMatcher(cv2.NORM_L2, crossCheck=True).match(des1, des2)
        verified = [
            m
            for m in matches
            if np.linalg.norm(
                cv2.perspectiveTransform(np.float32([[kp1[m.queryIdx].pt]]), matrix)[0, 0]
                - kp2[m.trainIdx].pt
            )
            < 3
        ][:40]
        return cv2.drawMatches(
            self.images[before],
            kp1,
            self.images[after],
            kp2,
            verified,
            None,
            flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
        )

    def _changes(self):
        remaining = sum(p.status == "comparable" for p in self.pairs)
        for pair in self.pairs:
            before, after = pair.before_id, pair.after_id
            if pair.status != "comparable":
                continue
            remaining -= 1
            warped, overlap = self.aligned[(before, after)]
            try:
                difference, regions = self._find_changes(
                    warped, self.images[after], overlap, self.config
                )
            except EPError as exc:
                if exc.code not in {"unstable_geometry", "insufficient_overlap"}:
                    raise
                pair.status = "inconclusive"
                pair.alignment_status = "rejected"
                pair.reasons.append(exc.code)
                continue
            self.writer.save("difference_map", (difference * 255).astype(np.uint8), [before, after])
            overlay = self.images[after].copy()
            # Reserve fixed artifacts for every selected pair before spending crop slots.
            available = max(0, (150 - len(self.writer.records) - 3 - remaining * 4) // 2)
            if len(regions) > available:
                self.candidates_truncated = True
                regions = regions[:available]
            for x, y, width, height, area, score in regions:
                after_box = normalized_box(x, y, width, height, overlap.shape)
                before_box = source_box(
                    (x, y, width, height),
                    self.geometries[(before, after)],
                    self.images[before].shape[:2],
                )
                bh, bw = self.images[before].shape[:2]
                crop = self.images[before][
                    int(before_box.y1 * bh) : max(
                        int(before_box.y1 * bh) + 1, int(before_box.y2 * bh)
                    ),
                    int(before_box.x1 * bw) : max(
                        int(before_box.x1 * bw) + 1, int(before_box.x2 * bw)
                    ),
                ]
                artifact_ids = [
                    self.writer.save("before_crop", crop, [before]),
                    self.writer.save(
                        "after_crop", self.images[after][y : y + height, x : x + width], [after]
                    ),
                ]
                self.candidates.append(
                    Candidate(
                        id=uuid4(),
                        before_id=before,
                        after_id=after,
                        before_box=before_box,
                        after_box=after_box,
                        area_pixels=area,
                        mean_difference=score,
                        inlier_ratio=pair.inlier_ratio,
                        method="masked_gain_offset_gaussian_ssim_v2_1",
                        artifact_ids=artifact_ids,
                    )
                )
                cv2.rectangle(overlay, (x, y), (x + width, y + height), (255, 80, 0), 2)
            self.writer.save("candidate_overlay", overlay, [before, after])
            boundary, notes = boundary_regions(
                self.masks[before],
                self.masks[after],
                self.geometries[(before, after)],
                self.config,
                aligned_before=warped,
                after=self.images[after],
            )
            self.boundary_limitations.extend(notes)
            boundary_map = np.zeros(self.images[after].shape[:2], np.uint8)
            boundary_overlay = self.images[after].copy()
            for region in boundary:
                x, y, width, height = region["box_xywh"]
                value = 255 if region["direction"] == "potentially_missing" else 128
                boundary_map[y : y + height, x : x + width] = value
                color = (255, 0, 180) if value == 255 else (0, 190, 255)
                cv2.rectangle(boundary_overlay, (x, y), (x + width, y + height), color, 2)
            boundary_ids = [
                self.writer.save("boundary_change_map", boundary_map, [before, after]),
                self.writer.save("boundary_overlay", boundary_overlay, [before, after]),
            ]
            for region in boundary:
                self.boundary_changes.append(
                    BoundaryChange(
                        id=uuid4(),
                        before_id=before,
                        after_id=after,
                        before_box=source_box(
                            region["box_xywh"],
                            self.geometries[(before, after)],
                            self.images[before].shape[:2],
                        ),
                        after_box=normalized_box(*region["box_xywh"], self.images[after].shape[:2]),
                        direction=region["direction"],
                        area_pixels=region["area_pixels"],
                        artifact_ids=boundary_ids,
                    )
                )
