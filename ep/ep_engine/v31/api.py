"""Local inspection functions. Never call a VLM, database or settlement service."""

import time

import cv2
import numpy as np

from ep_engine.core.exceptions import EPError
from ep_engine.cv.worker import load_inputs
from ep_engine.v31.contracts import (
    CaptureGuidance,
    DetailCrop,
    IdentityAssessment,
    InspectionReport,
    InspectionRequest,
    InstanceAssociation,
    ViewAssessment,
)
from ep_engine.v31.coordinates import crop_frame, original_transform, resize_frame
from ep_engine.v31.pipeline import InspectionPipeline, mask_components
from ep_engine.v31.surfaces import observe_surfaces


def inspect(payload, artifact_dir, *, models=None, learned=None):
    request = InspectionRequest.model_validate(payload)
    inputs = load_inputs(request.model_dump(mode="json"), preserve_original=True)
    return inspect_inputs(
        request.inspection_id,
        inputs,
        artifact_dir,
        request.config,
        models=models,
        learned=learned,
        instance_ids={row.id: row.instance_id for row in request.evidence},
        high_resolution_crops=request.high_resolution_crops,
        surface_observation_budget=request.surface_observation_budget,
    )


def _near(first, second):
    # Deliberately conservative dependence grouping; never increases corroboration.
    a, b = [
        cv2.resize(
            cv2.cvtColor(image, cv2.COLOR_RGB2GRAY), (32, 32), interpolation=cv2.INTER_AREA
        ).astype(np.float32)
        / 255
        for image in (first, second)
    ]
    return float(np.mean(np.abs(a - b))) <= 0.02


def _fusion(package, images):
    groups = []
    for pair in package.pairs:
        if pair.status != "comparable":
            continue
        for group in groups:
            reference = group[0]
            if _near(images[pair.before_id], images[reference.before_id]) and _near(
                images[pair.after_id], images[reference.after_id]
            ):
                group.append(pair)
                break
        else:
            groups.append([pair])
    return {
        "scope": "localized_view_observations_only",
        "observation_groups": [
            [{"before_id": str(p.before_id), "after_id": str(p.after_id)} for p in group]
            for group in groups
        ],
        "independent_support_count": None,
        "cross_view_region_correspondence": "not_established",
        "contradiction_assessment": "not_established_without_cross_view_surface_mapping",
        "whole_object_condition": "inconclusive",
        "damage_attribution": "abstained_identity_and_physical_cause_unverified",
        "unobservable_regions": (
            "All surfaces outside verified per-view overlap; unseen sides unknown"
        ),
    }


def _details(pipeline, package, inputs, budget):
    """Bounded original-data review crops. These never add damage/change proposals."""
    originals = {
        row.id: row.original_rgb if row.original_rgb is not None else row.rgb for row in inputs
    }
    crops = []
    for candidate in package.candidates:
        if len(crops) >= budget or len(pipeline.writer.records) > 147:
            break
        # A conservative PNG byte reserve prevents partial writes at the 32 MB cap.
        if pipeline.writer.total + 8_000_000 > 32_000_000:
            break
        before, after = candidate.before_id, candidate.after_id
        image0, image1 = originals[before], originals[after]
        h0, w0 = image0.shape[:2]
        h1, w1 = image1.shape[:2]
        ph0, pw0 = pipeline.images[before].shape[:2]
        ph1, pw1 = pipeline.images[after].shape[:2]
        if (w0, h0, w1, h1) == (pw0, ph0, pw1, ph1):
            continue
        box = candidate.after_box
        x1, y1 = max(0, int(box.x1 * w1) - 8), max(0, int(box.y1 * h1) - 8)
        x2, y2 = min(w1, int(np.ceil(box.x2 * w1)) + 8), min(h1, int(np.ceil(box.y2 * h1)) + 8)
        scale = min(1.0, 1024 / max(x2 - x1, y2 - y1))
        width, height = max(1, round((x2 - x1) * scale)), max(1, round((y2 - y1) * scale))
        transform = original_transform(
            pipeline.geometries[(before, after)], (ph0, pw0), (ph1, pw1), (h0, w0), (h1, w1)
        )
        crop_transform = crop_frame((x1, y1, x2, y2), (width, height))
        target = cv2.warpPerspective(image1, crop_transform, (width, height))
        warped = cv2.warpPerspective(image0, crop_transform @ transform, (width, height))
        valid = cv2.warpPerspective(
            pipeline.aligned[(before, after)][1].astype(np.uint8),
            crop_transform @ resize_frame((ph1, pw1), (h1, w1)),
            (width, height),
            flags=cv2.INTER_NEAREST,
        ).astype(bool)
        warped[~valid] = 0
        target[~valid] = 0
        ids = [
            pipeline.writer.save("before_crop", warped, [before]),
            pipeline.writer.save("after_crop", target, [after]),
            pipeline.writer.save("valid_overlap", valid.astype(np.uint8) * 255, [before, after]),
        ]
        crops.append(
            DetailCrop(
                before_id=before,
                after_id=after,
                candidate_id=candidate.id,
                after_box={"x1": x1 / w1, "y1": y1 / h1, "x2": x2 / w1, "y2": y2 / h1},
                width=width,
                height=height,
                artifact_ids=ids,
                sampling_floor_source_pixels=2
                * max(
                    (x2 - x1) / width,
                    (y2 - y1) / height,
                    1 / pipeline._comparison_scale(transform, image0.shape[:2]),
                ),
            )
        )
    package.artifacts = pipeline.writer.records.copy()
    return crops


def inspect_inputs(
    inspection_id,
    inputs,
    artifact_dir,
    config,
    *,
    models=None,
    learned=None,
    instance_ids=None,
    high_resolution_crops=4,
    surface_observation_budget=4,
):
    """In-memory RGB adapter: input arrays are orientation-corrected, immutable sources.

    instance_ids are operator grouping hints, never proof of physical identity.
    Use explicit tight targets in separate captures for independently movable instances.
    """
    if not 0 <= high_resolution_crops <= 8:
        raise ValueError("Detail crop budget must be between zero and eight")
    if not 0 <= surface_observation_budget <= 8:
        raise ValueError("Surface observation budget must be between zero and eight")
    for row in inputs:
        for image in (row.rgb, row.original_rgb):
            if image is None:
                continue
            if (
                not isinstance(image, np.ndarray)
                or image.dtype != np.uint8
                or image.ndim != 3
                or image.shape[2] != 3
                or min(image.shape[:2]) < 1
                or image.shape[0] * image.shape[1] > 16_000_000
            ):
                raise EPError(413, "processing_limit", "Invalid source image collection")
        if row.original_rgb is not None and row.original_size != (
            row.original_rgb.shape[1],
            row.original_rgb.shape[0],
        ):
            raise EPError(422, "invalid_evidence", "Original source dimensions differ from pixels")
    if (
        sum(
            (row.original_rgb if row.original_rgb is not None else row.rgb).shape[0]
            * (row.original_rgb if row.original_rgb is not None else row.rgb).shape[1]
            for row in inputs
        )
        > 64_000_000
    ):
        raise ValueError("Original image collection exceeds memory budget")
    started = time.perf_counter()
    pipeline = InspectionPipeline(config, models, learned, instance_ids)
    package = pipeline.run(inspection_id, inputs, artifact_dir)
    identity, views, guidance = [], [], []
    source = {row.id: row for row in inputs}
    instances = [
        InstanceAssociation(
            evidence_id=row.id,
            instance_id=pipeline.instance_ids.get(row.id),
            source="operator_target_metadata"
            if pipeline.instance_ids.get(row.id)
            else "unspecified",
            significant_mask_components=mask_components(pipeline.masks[row.id])
            if row.id in pipeline.masks
            else 0,
        )
        for row in inputs
    ]
    for quality in package.quality:
        for reason, recommendation in zip(quality.reasons, quality.recommendations, strict=True):
            guidance.append(
                CaptureGuidance(
                    source_ids=[quality.evidence_id],
                    category="input_quality",
                    reason=reason,
                    recommendation=recommendation,
                )
            )
    for segment in package.segmentation:
        if segment.status != "segmented":
            guidance.append(
                CaptureGuidance(
                    source_ids=[segment.evidence_id],
                    category="input_quality",
                    reason="surface_not_assessable",
                    recommendation=(
                        "Select one complete object with a tight target and clear surface detail"
                    ),
                )
            )
    for pair in package.pairs:
        before, after = pair.before_id, pair.after_id
        first = (
            source[before].original_rgb
            if source[before].original_rgb is not None
            else source[before].rgb
        )
        second = (
            source[after].original_rgb
            if source[after].original_rgb is not None
            else source[after].rgb
        )
        originals_equal = first.shape == second.shape and np.array_equal(first, second)
        relation = (
            "same_capture"
            if originals_equal
            else "local_visual_consistency"
            if pair.homography is not None
            else "inconsistent_visual_evidence"
            if pair.cosine_similarity < config.min_similarity
            else "embedding_similarity_only"
        )
        identity.append(
            IdentityAssessment(
                before_id=before,
                after_id=after,
                visual_relation=relation,
                reasons=[
                    "Visual similarity and geometry cannot prove physical identity",
                    "No independently verified distinctive identifier is available",
                ],
            )
        )
        candidates = [
            r.id for r in package.candidates if (r.before_id, r.after_id) == (before, after)
        ]
        boundaries = [
            r.id for r in package.boundary_changes if (r.before_id, r.after_id) == (before, after)
        ]
        aligned = pair.status == "comparable"
        ah, aw = pipeline.images[after].shape[:2]
        original_width, original_height = package.source_dimensions[after]
        source_scale = max(original_width / aw, original_height / ah)
        sampling = (
            1
            / pipeline._sampling_scale(pipeline.geometries[(before, after)], pipeline.masks[before])
            if aligned
            else 1
        )
        notes = [
            "identity_unverified",
            "Fine features below the sampling floor are not assessable",
            "Lighting, reflection, shadow, pose and movable components can explain differences",
            "No conclusion about unseen surfaces or function",
            *pair.reasons,
        ]
        views.append(
            ViewAssessment(
                before_id=before,
                after_id=after,
                source_ids=[before, after],
                observation="not_assessable"
                if not aligned
                else "observed_appearance_difference"
                if candidates or boundaries
                else "no_localized_change_detected",
                assessable_after_fraction=pair.overlap_fraction if aligned else 0,
                unassessed_after_fraction=1 - pair.overlap_fraction if aligned else 1,
                sampling_floor_after_source_pixels=2 * source_scale * sampling if aligned else None,
                localization_uncertainty_after_source_pixels=max(
                    1.0, pair.symmetric_reprojection_error or 0
                )
                * source_scale
                if aligned
                else None,
                candidate_ids=candidates,
                boundary_ids=boundaries,
                uncertainty_reasons=notes,
            )
        )
        guidance.append(
            CaptureGuidance(
                source_ids=[before, after],
                category="identity",
                reason="identity_unverified",
                recommendation=(
                    "Include the same distinctive marking or visible identifier in matched views"
                ),
            )
        )
        if not aligned:
            reason = pair.reasons[-1] if pair.reasons else "viewpoint_mismatch"
            instances_uncertain = "instance" in reason
            guidance.append(
                CaptureGuidance(
                    source_ids=[before, after],
                    category="instances" if instances_uncertain else "geometry",
                    reason=reason,
                    recommendation=(
                        "Photograph each movable item separately with one tight target per instance"
                        if instances_uncertain
                        else "Rephotograph the same side at a similar angle with less glare "
                        "and visible surface detail"
                    ),
                )
            )
        else:
            guidance.append(
                CaptureGuidance(
                    source_ids=[before, after],
                    category="resolution",
                    reason="fine_detail_not_exhaustively_assessed",
                    recommendation=(
                        "Capture matched original-resolution closeups of suspected scratches "
                        "with diffuse illumination"
                    ),
                )
            )
    # Requested views excluded by view labels or pair budgets remain explicitly unobserved.
    if package.unmatched_ids:
        guidance.append(
            CaptureGuidance(
                source_ids=package.unmatched_ids,
                category="common_surface",
                reason="unmatched_views",
                recommendation=(
                    "Capture the missing matched angle with the relevant component visible"
                ),
            )
        )
    details = _details(pipeline, package, inputs, high_resolution_crops)
    surfaces = observe_surfaces(pipeline, package, inputs, surface_observation_budget)
    metrics = {
        **package.metrics,
        "inspection_seconds": time.perf_counter() - started,
        "detail_crop_count": len(details),
        "detail_crop_budget": high_resolution_crops,
        "sampling_domain": "analytic_object_mask_bounding_rectangle",
        "surface_observation_count": len(surfaces),
        "surface_observation_budget": surface_observation_budget,
    }
    if pipeline.models is not None:
        metrics.update(pipeline.models.metrics())
    return InspectionReport(
        inspection_id=inspection_id,
        cv_package=package,
        identity=identity,
        instances=instances,
        views=views,
        detail_crops=details,
        surface_observations=surfaces,
        recapture_guidance=guidance,
        fusion=_fusion(package, pipeline.images),
        runtime=metrics,
        limitations=[
            *package.limitations,
            "Physical identity remains unverified; object-specific damage attribution abstained",
            "Sampling floor is a pixel sampling bound, not calibrated defect detectability",
            "Original-data crops are bounded review aids; they do not establish damage",
            "Only cited original-resolution tiles were re-examined; "
            "remaining fine detail is unassessed",
            "Mask components do not resolve overlapping instances; use separate tight targets",
            "No calibrated confidence probabilities or cross-view surface identity are available",
        ],
    )
