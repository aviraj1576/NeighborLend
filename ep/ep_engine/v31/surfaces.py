"""Bounded original-pixel examination, including local evidence on rejected pairs."""

import cv2
import numpy as np

from ep_engine.cv.pipeline import normalized_box
from ep_engine.v31.contracts import SurfaceObservation
from ep_engine.v31.coordinates import crop_frame, original_transform, resize_frame


def observe_surfaces(pipeline, package, inputs, budget):
    if budget == 0:
        return []
    sources = {r.id: r.original_rgb if r.original_rgb is not None else r.rgb for r in inputs}
    tasks = []
    for region in pipeline.local_surfaces:
        tasks.append(
            (
                region["before_id"],
                region["after_id"],
                region["matrix"],
                region["overlap"],
                "local_correspondence_hull",
                region["support"],
            )
        )
    for pair in package.pairs:
        if pair.status != "comparable":
            continue
        key = (pair.before_id, pair.after_id)
        # A native scan only adds resolution when the original has more samples.
        original, processed = sources[pair.after_id], pipeline.images[pair.after_id]
        if max(original.shape[:2]) <= max(processed.shape[:2]):
            continue
        tasks.append(
            (
                *key,
                pipeline.geometries[key],
                pipeline.aligned[key][1],
                "original_resolution_tile",
                dict(
                    inliers=pair.inliers,
                    inlier_ratio=pair.inlier_ratio,
                    symmetric_reprojection_error=pair.symmetric_reprojection_error,
                ),
            )
        )
    observations = []
    queues = []
    for before, after, matrix, overlap, scope, support in tasks:
        ys, xs = np.where(overlap)
        if not len(xs):
            continue
        image0, image1 = sources[before], sources[after]
        h0, w0 = image0.shape[:2]
        h1, w1 = image1.shape[:2]
        ph0, pw0 = pipeline.images[before].shape[:2]
        ph1, pw1 = overlap.shape
        transform = original_transform(matrix, (ph0, pw0), (ph1, pw1), (h0, w0), (h1, w1))
        # Conservative original-data sampling, no interpolated detail claims.
        scale = pipeline._comparison_scale(transform, image0.shape[:2])
        x0, y0 = int(xs.min() * w1 / pw1), int(ys.min() * h1 / ph1)
        x2, y2 = (
            min(w1, int(np.ceil((xs.max() + 1) * w1 / pw1))),
            min(h1, int(np.ceil((ys.max() + 1) * h1 / ph1))),
        )
        # Fixed spatial ordering, independent of observed residuals. Four windows
        # maximum per view, distributed round-robin across available views.
        side = max(1, int(1024 / scale))
        tiles = [
            (x, y, min(x + side, x2), min(y + side, y2))
            for y in range(y0, y2, side)
            for x in range(x0, x2, side)
        ][:4]
        queues.append(
            [(before, after, transform, overlap, scope, support, scale, box) for box in tiles]
        )
    for round_index in range(4):
        for queue in queues:
            if round_index >= len(queue):
                continue
            if (
                len(observations) >= budget
                or len(pipeline.writer.records) > 146
                or pipeline.writer.total + 10_000_000 > 32_000_000
            ):
                package.artifacts = pipeline.writer.records.copy()
                return observations
            before, after, transform, overlap, scope, support, scale, box = queue[round_index]
            image0, image1 = sources[before], sources[after]
            h1, w1 = image1.shape[:2]
            ph1, pw1 = overlap.shape
            x, y, right, bottom = box
            width, height = max(1, round((right - x) * scale)), max(1, round((bottom - y) * scale))
            sx, sy = width / (right - x), height / (bottom - y)
            crop = crop_frame(box, (width, height))
            warped = cv2.warpPerspective(image0, crop @ transform, (width, height))
            # Match sampling kernels/centers in both frames; unequal AREA versus
            # linear resampling can create residuals on unchanged fine texture.
            target = cv2.warpPerspective(image1, crop, (width, height))
            valid = cv2.warpPerspective(
                overlap.astype(np.uint8),
                crop @ resize_frame((ph1, pw1), (h1, w1)),
                (width, height),
                flags=cv2.INTER_NEAREST,
            ).astype(bool)
            # SSIM neighborhoods must remain inside observed support and tile.
            valid = cv2.erode(
                valid.astype(np.uint8),
                np.ones((7, 7), np.uint8),
                borderType=cv2.BORDER_CONSTANT,
                borderValue=0,
            ).astype(bool)
            if valid.sum() < 64 or min(width, height) < 8:
                continue
            difference, regions = pipeline._appearance(
                warped, target, valid, pipeline.config.model_copy(update={"max_side": 1024})
            )
            warped[~valid] = 0
            target[~valid] = 0
            ids = [
                pipeline.writer.save(kind, data, cited)
                for kind, data, cited in (
                    ("before_crop", warped, [before]),
                    ("after_crop", target, [after]),
                    ("valid_overlap", valid.astype(np.uint8) * 255, [before, after]),
                    ("difference_map", (difference * 255).astype(np.uint8), [before, after]),
                )
            ]
            boxes = [
                normalized_box(x + rx / sx, y + ry / sy, rw / sx, rh / sy, (h1, w1))
                for rx, ry, rw, rh, _, _ in regions
            ]
            observations.append(
                SurfaceObservation(
                    before_id=before,
                    after_id=after,
                    scope=scope,
                    after_box=normalized_box(x, y, right - x, bottom - y, (h1, w1)),
                    width=width,
                    height=height,
                    valid_fraction=float(valid.mean()),
                    assessed_after_mask_fraction=min(
                        1.0,
                        float(
                            valid.sum()
                            / (sx * sy)
                            / (w1 / pw1 * h1 / ph1)
                            / pipeline.masks[after].sum()
                        ),
                    ),
                    sampling_floor_source_pixels=2 * max(1 / sx, 1 / sy),
                    registration_uncertainty_source_pixels=max(
                        1.0, support.get("symmetric_reprojection_error") or 0
                    )
                    * max(w1 / pw1, h1 / ph1),
                    appearance_regions=boxes,
                    artifact_ids=ids,
                    geometry_support=support,
                    uncertainty_reasons=[
                        "physical_identity_unverified",
                        "reflection_lighting_pose_and_registration_can_explain_residuals",
                        "sampling_floor_is_not_validated_defect_detectability",
                        "unscanned_surfaces_remain_unknown",
                        *(
                            ["local_geometry_does_not_validate_the_whole_view"]
                            if scope == "local_correspondence_hull"
                            else []
                        ),
                    ],
                )
            )
    package.artifacts = pipeline.writer.records.copy()
    return observations
