import hashlib
import io
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from ep_engine.assessment.engine import supported_pairs
from ep_engine.config import EP_ROOT
from ep_engine.cv.worker import load_inputs
from ep_engine.v31.contracts import InspectionReport, InspectionRequest


def verified_pairs(package):
    return [
        p
        for p in supported_pairs(package)
        if p.symmetric_reprojection_error is not None
        and p.symmetric_reprojection_error <= 3
        and min(p.source_coverage, p.target_coverage) >= 0.03
    ]


def safe_path(path):
    path = Path(path)
    resolved = path.resolve()
    if path.is_symlink() or not resolved.is_relative_to(EP_ROOT.resolve()):
        raise ValueError("Evaluation paths must stay inside EP")
    # Reject links/junction escapes in every supplied parent, too.
    if any(
        p.is_symlink() or bool(getattr(p.lstat(), "st_file_attributes", 0) & 0x400)
        for p in (path, *path.parents)
        if p.exists()
    ):
        raise ValueError("Linked evaluation paths are not permitted")
    return resolved


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pixel_sha(rgb):
    """Hash the same RGB bytes without an image-sized temporary bytes allocation."""
    return sha(memoryview(np.ascontiguousarray(rgb)))


def checked_bytes(path, digest, maximum=20_000_000):
    path = safe_path(path)
    if path.stat().st_size > maximum:
        raise ValueError("Evidence byte limit exceeded")
    data = path.read_bytes()
    if sha(data) != digest:
        raise ValueError("Evidence digest mismatch")
    return data


def verified_case(case):
    payload = json.loads(checked_bytes(case.input_manifest, case.input_sha256, 1_000_000))
    request = InspectionRequest.model_validate(payload)
    report = InspectionReport.model_validate_json(
        checked_bytes(case.cv_report, case.cv_sha256, 2_000_000)
    )
    package = report.cv_package
    inputs = load_inputs(request.model_dump(mode="json"), preserve_original=True)
    if request.inspection_id != report.inspection_id or {i.id for i in inputs} != set(
        package.source_ids
    ):
        raise ValueError("CV report does not match the original captures")
    for row in inputs:
        if (
            package.source_hashes[row.id] != row.sha256
            or package.source_dimensions[row.id] != row.original_size
        ):
            raise ValueError("CV source provenance mismatch")
    artifacts = {}
    for artifact in package.artifacts:
        data = checked_bytes(
            case.cv_report.parent / "artifacts" / f"{artifact.id}.png", artifact.sha256
        )
        if len(data) != artifact.byte_size:
            raise ValueError("CV artifact size mismatch")
        with Image.open(io.BytesIO(data), formats=("PNG",)) as image:
            if image.size != (artifact.width, artifact.height):
                raise ValueError("CV artifact dimensions mismatch")
            image.verify()
        artifacts[artifact.id] = data
    return request, report, inputs, artifacts


def prepare(case, mode, limits, verified):
    request, report, inputs, artifacts = verified
    images = []
    total = 0
    for row in inputs:
        rgb = row.original_rgb
        stream = io.BytesIO()
        # Original source-resolution pixels; re-encoding removes EXIF/GPS/text chunks.
        Image.fromarray(rgb).save(stream, format="PNG")
        data = stream.getvalue()
        total += len(data)
        images.append(
            dict(
                id=str(row.id),
                kind="original_capture",
                stage=row.stage,
                width=rgb.shape[1],
                height=rgb.shape[0],
                data=data,
            )
        )
    evidence = dict(
        coordinate_system="normalized_orientation_corrected_source",
        images=[{k: v for k, v in row.items() if k != "data"} for row in images],
        source_pairs=[
            dict(before_id=str(b.id), after_id=str(a.id))
            for b in inputs
            if b.stage == "before"
            for a in inputs
            if a.stage == "after"
            and (not b.view or not a.view or b.view.strip().casefold() == a.view.strip().casefold())
        ],
    )
    if mode == "hybrid":
        package = report.cv_package
        pairs = verified_pairs(package)
        evidence["cv"] = dict(
            outcome=package.outcome,
            verified_pairs=[p.model_dump(mode="json") for p in pairs],
            rejected_pairs=[
                dict(before_id=str(p.before_id), after_id=str(p.after_id), reasons=p.reasons)
                for p in package.pairs
                if p not in pairs
            ],
            candidates=[c.model_dump(mode="json") for c in package.candidates],
            limitations=report.limitations,
        )
        # Cap evidence additions; raw originals are identical across both VLM arms.
        needed = [p.overlap_id for p in pairs]
        needed.extend(i for c in package.candidates for i in c.artifact_ids)
        metadata = {a.id: a for a in package.artifacts}
        for identifier in dict.fromkeys(needed):
            a = metadata[identifier]
            data = artifacts[identifier]
            if len(images) >= limits.max_images or total + len(data) > limits.max_image_bytes:
                break
            images.append(
                dict(
                    id=str(identifier),
                    kind=a.kind,
                    source_ids=list(map(str, a.source_ids)),
                    width=a.width,
                    height=a.height,
                    data=data,
                )
            )
            total += len(data)
        evidence["allowed_artifact_ids"] = [
            r["id"] for r in images if r["kind"] != "original_capture"
        ]
    if len(images) > limits.max_images or total > limits.max_image_bytes:
        raise ValueError("Request original-image budget exceeded; select a smaller collection")
    # Labels, filenames, case/category names and local paths never enter the model input.
    return dict(
        evidence=evidence,
        images=images,
        original_ids=[str(r.id) for r in inputs],
        input_pixels_sha256={str(r.id): pixel_sha(r.original_rgb) for r in inputs},
    )


def validate_citations(reply, prepared):
    sources = set(prepared["original_ids"])
    attached = {r["id"] for r in prepared["images"]}
    allowed = {(p["before_id"], p["after_id"]) for p in prepared["evidence"]["source_pairs"]}
    for observation in reply.observations:
        key = (str(observation.before_id), str(observation.after_id))
        if (
            key not in allowed
            or str(observation.before_region.image_id) != key[0]
            or str(observation.after_region.image_id) != key[1]
        ):
            raise ValueError("Observation cites an unsupported source pair/frame")
        cited = set(map(str, observation.evidence_ids))
        if not set(key) <= cited or not cited <= attached or not set(key) <= sources:
            raise ValueError("Observation has ungrounded evidence citations")


def cv_prediction(report):
    package = report.cv_package
    pairs = verified_pairs(package)
    if not pairs:
        return None
    allowed = {(p.before_id, p.after_id) for p in pairs}
    changed = any(
        (r.before_id, r.after_id) in allowed
        for r in (*package.candidates, *package.boundary_changes)
    ) or any(
        s.appearance_regions and (s.before_id, s.after_id) in allowed
        for s in report.surface_observations
    )
    return True if changed else False if package.outcome == "comparable" else None


def constrained_prediction(reply, mode, report, prepared):
    validate_citations(reply, prepared)
    if reply.change == "uncertain":
        return None, "vlm_abstained"
    if mode == "vlm_only":
        return reply.change == "visible_difference", "unverified_visual_interpretation"
    pairs = {(str(p.before_id), str(p.after_id)): p for p in verified_pairs(report.cv_package)}
    if not pairs:
        return None, "unverified_visual_only_cv_geometry_inconclusive"
    if reply.change == "no_visible_difference":
        if report.cv_package.outcome != "comparable" or not pairs or cv_prediction(report) is True:
            return None, "cv_uncertainty_or_positive_evidence_cannot_be_overridden"
        return False, "no_difference_in_cv_assessed_scope_only"
    inputs = {r["id"]: r for r in prepared["images"] if r["kind"] == "original_capture"}
    for observation in reply.observations:
        key = (str(observation.before_id), str(observation.after_id))
        pair = pairs.get(key)
        if pair is None:
            return None, "unsupported_geometry_cannot_be_overridden"
        # Every positive region must lie wholly inside the verified overlap.
        # An image citation plus model assertion cannot create observable geometry.
        with Image.open(io.BytesIO(prepared["_artifacts"][pair.overlap_id])) as overlap:
            mask = np.asarray(overlap) > 0
        x1, y1, x2, y2 = observation.after_region.box
        h, w = mask.shape
        region = mask[
            int(y1 * h) : max(int(y1 * h) + 1, int(np.ceil(y2 * h))),
            int(x1 * w) : max(int(x1 * w) + 1, int(np.ceil(x2 * w))),
        ]
        if region.size == 0 or not region.all():
            return None, "claimed_region_outside_verified_overlap"
        # Validate the reference box as well; unsupported pixels in either source
        # cannot become evidence merely by pairing them with a supported after box.
        bw, bh = report.cv_package.processing_dimensions[observation.before_id]
        inverse = cv2.warpPerspective(
            mask.astype(np.uint8),
            np.linalg.inv(np.asarray(pair.homography)),
            (bw, bh),
            flags=cv2.INTER_NEAREST,
        )
        bx1, by1, bx2, by2 = observation.before_region.box
        reference = inverse[
            int(by1 * bh) : max(int(by1 * bh) + 1, int(np.ceil(by2 * bh))),
            int(bx1 * bw) : max(int(bx1 * bw) + 1, int(np.ceil(bx2 * bw))),
        ]
        if reference.size == 0 or not reference.all():
            return None, "claimed_reference_outside_verified_overlap"
        points = np.array(
            [
                [
                    [bx1 * bw, by1 * bh],
                    [bx2 * bw, by1 * bh],
                    [bx2 * bw, by2 * bh],
                    [bx1 * bw, by2 * bh],
                ]
            ],
            np.float32,
        )
        projected = cv2.perspectiveTransform(points, np.asarray(pair.homography))[0] / np.array(
            [w, h]
        )
        low, high = projected.min(axis=0), projected.max(axis=0)
        if high[0] <= x1 or low[0] >= x2 or high[1] <= y1 or low[1] >= y2:
            return None, "claimed_regions_do_not_correspond_geometrically"
        if key[0] not in inputs or key[1] not in inputs:
            return None, "source_not_attached"
    if cv_prediction(report) is False:
        return None, "cv_vlm_disagreement_requires_human_review"
    return True, "geometry_supported_appearance_hypothesis_only"
