import hashlib
import io
import time
from uuid import UUID

import numpy as np
from PIL import Image

from ep_engine.assessment.contracts import AssessmentReport, ProviderReply, digest_package
from ep_engine.assessment.providers import PreparedRequest, ProviderError, UnavailableProvider
from ep_engine.core.exceptions import EPError
from ep_engine.cv.contracts import CVPackage
from ep_engine.cv.geometry import validate_transform
from ep_engine.pipeline.interfaces import PipelineContext, StageResult
from ep_engine.pipeline.orchestrator import Orchestrator


def supported_pairs(package):
    quality = {row.evidence_id: row for row in package.quality}
    segments = {row.evidence_id: row for row in package.segmentation}
    artifacts = {row.id: row for row in package.artifacts}
    valid = []
    for pair in package.pairs:
        if (
            pair.status != "comparable"
            or pair.alignment_status != "aligned"
            or pair.identity != "consistent_visual_evidence"
            or not pair.local_matching_evaluated
            or pair.cosine_similarity < package.thresholds.min_similarity
            or not pair.matches >= pair.inliers >= package.thresholds.min_inliers
            or pair.inlier_ratio < package.thresholds.min_inlier_ratio
            or pair.median_reprojection_error is None
            or pair.median_reprojection_error > 3
            or pair.overlap_fraction < package.thresholds.min_overlap
            or any(
                quality[key].status != "usable" or segments[key].status != "segmented"
                for key in (pair.before_id, pair.after_id)
            )
        ):
            continue
        overlap = artifacts.get(pair.overlap_id)
        if (
            overlap is None
            or overlap.kind != "valid_overlap"
            or set(overlap.source_ids) != {pair.before_id, pair.after_id}
        ):
            continue
        try:
            bw, bh = package.processing_dimensions[pair.before_id]
            aw, ah = package.processing_dimensions[pair.after_id]
            validate_transform(np.asarray(pair.homography, dtype=float), (bh, bw), (ah, aw))
        except (EPError, ValueError, TypeError):
            continue
        valid.append(pair)
    return valid


def prepare(package, pairs, read_artifact, options):
    artifacts = {row.id: row for row in package.artifacts}
    pair_map = {(p.before_id, p.after_id): p for p in pairs[: options.max_pairs]}
    selected, images, attached = [], [], set()
    total = 0
    for candidate in sorted(
        package.candidates, key=lambda row: row.area_pixels * row.mean_difference, reverse=True
    ):
        if len(selected) >= options.max_candidates:
            break
        pair = pair_map.get((candidate.before_id, candidate.after_id))
        if pair is None:
            continue
        required = list(candidate.artifact_ids)
        crops = [artifacts[key] for key in required if key in artifacts]
        if not (
            {"before_crop", "after_crop"} <= {row.kind for row in crops}
            and all(set(row.source_ids).issubset({pair.before_id, pair.after_id}) for row in crops)
        ):
            continue
        if not (
            any(row.kind == "before_crop" and row.source_ids == [pair.before_id] for row in crops)
            and any(row.kind == "after_crop" and row.source_ids == [pair.after_id] for row in crops)
        ):
            continue
        contexts = [
            next(
                (
                    a
                    for a in artifacts.values()
                    if a.kind == "object_crop" and a.source_ids == [key]
                ),
                None,
            )
            for key in (pair.before_id, pair.after_id)
        ]
        if any(row is None for row in contexts):
            continue
        required.extend(row.id for row in contexts)
        required.extend(
            a.id
            for a in artifacts.values()
            if a.kind in ("candidate_overlay", "valid_overlap")
            and set(a.source_ids) == {pair.before_id, pair.after_id}
        )
        needed = [key for key in dict.fromkeys(required) if key not in attached]
        if len(images) + len(needed) > 16:
            continue
        pending, pending_bytes = [], 0
        for key in needed:
            metadata = artifacts[key]
            data = read_artifact(key)
            if (
                len(data) != metadata.byte_size
                or hashlib.sha256(data).hexdigest() != metadata.sha256
            ):
                raise ProviderError("artifact_integrity")
            with Image.open(io.BytesIO(data), formats=("PNG",)) as original:
                if original.size != (metadata.width, metadata.height):
                    raise ProviderError("artifact_integrity")
                original.load()
                image = original.convert("RGB")
                image.thumbnail((options.image_side, options.image_side))
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
            encoded = buffer.getvalue()
            if len(encoded) > 1_000_000:
                raise ProviderError("evidence_budget")
            pending_bytes += len(encoded)
            frame = (
                pair.after_id
                if metadata.kind in ("candidate_overlay", "valid_overlap")
                else metadata.source_ids[0]
            )
            source_box = {"x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 1.0}
            if metadata.kind == "before_crop":
                source_box = candidate.before_box.model_dump()
            elif metadata.kind == "after_crop":
                source_box = candidate.after_box.model_dump()
            elif metadata.kind == "object_crop":
                segment = next(row for row in package.segmentation if row.evidence_id == frame)
                source_box = segment.box.model_dump()
            pending.append(
                {
                    "artifact_id": str(key),
                    "source_ids": list(map(str, metadata.source_ids)),
                    "kind": metadata.kind,
                    "media_type": "image/png",
                    "sha256": hashlib.sha256(encoded).hexdigest(),
                    "source_artifact_sha256": metadata.sha256,
                    "width": image.width,
                    "height": image.height,
                    "frame_evidence_id": str(frame),
                    "source_box": source_box,
                    "data": encoded,
                }
            )
        if total + pending_bytes > 8_000_000:
            continue
        images.extend(pending)
        attached.update(needed)
        total += pending_bytes
        selected.append(candidate)
    sources = {key for candidate in selected for key in (candidate.before_id, candidate.after_id)}
    selected_pairs = {(candidate.before_id, candidate.after_id) for candidate in selected}
    return PreparedRequest(
        {
            "inspection_id": str(package.inspection_id),
            "cv_digest": digest_package(package),
            "coordinate_system": package.coordinate_system,
            "source_hashes": {
                str(key): value for key, value in package.source_hashes.items() if key in sources
            },
            "source_dimensions": {
                str(key): value
                for key, value in package.source_dimensions.items()
                if key in sources
            },
            "processing_dimensions": {
                str(key): value
                for key, value in package.processing_dimensions.items()
                if key in sources
            },
            "candidates": [row.model_dump(mode="json") for row in selected],
            "pairs": [
                row.model_dump(mode="json")
                for row in pairs[: options.max_pairs]
                if (row.before_id, row.after_id) in selected_pairs
            ],
            "segmentation": [
                row.model_dump(mode="json")
                for row in package.segmentation
                if row.evidence_id in sources
            ],
            "quality": [
                row.model_dump(mode="json") for row in package.quality if row.evidence_id in sources
            ],
            "allowed_artifact_ids": [row["artifact_id"] for row in images],
            "limitations": package.limitations,
            "response_schema": ProviderReply.model_json_schema(),
        },
        images,
    ), selected


def validate_reply(reply, selected, request):
    allowed = {row.id: row for row in selected}
    attached = {
        UUID(row["artifact_id"]): set(map(UUID, row["source_ids"])) for row in request.images
    }
    seen = set()
    for observation in reply.observations:
        candidate = allowed.get(observation.candidate_id)
        if candidate is None or observation.candidate_id in seen:
            raise ProviderError("unsupported_claim")
        seen.add(observation.candidate_id)
        sources = {candidate.before_id, candidate.after_id}
        if (
            set(observation.evidence_ids) != sources
            or not set(candidate.artifact_ids).issubset(set(observation.artifact_ids))
            or any(
                key not in attached or not attached[key].issubset(sources)
                for key in observation.artifact_ids
            )
        ):
            raise ProviderError("unsupported_claim")
    if seen != set(allowed):
        raise ProviderError("unsupported_claim")


def repeated_regions(selected, observations):
    """Use shared source coordinates only; no guessed cross-capture physical identity."""
    findings = {row.candidate_id: row for row in observations}
    repeated, conflicts = set(), set()
    for index, first in enumerate(selected):
        for second in selected[index + 1 :]:
            boxes = [
                (first.before_id, first.before_box, second.before_id, second.before_box),
                (first.after_id, first.after_box, second.after_id, second.after_box),
            ]
            if not any(
                a == b and min(x.x2, y.x2) > max(x.x1, y.x1) and min(x.y2, y.y2) > max(x.y1, y.y1)
                for a, x, b, y in boxes
            ):
                continue
            repeated.update((first.id, second.id))
            statuses = {findings[first.id].status, findings[second.id].status}
            if "possible_visible_damage" in statuses and statuses.intersection(
                {"no_visible_change", "visual_artifact"}
            ):
                conflicts.update((first.id, second.id))
    return repeated, conflicts


def assess(cv_run_id, package, read_artifact, options, provider=None):
    started = time.perf_counter()
    package = CVPackage.model_validate(package.model_dump())
    provider = provider or UnavailableProvider()
    report = AssessmentReport(
        cv_run_id=cv_run_id,
        inspection_id=package.inspection_id,
        cv_digest=digest_package(package),
        source_hashes=package.source_hashes,
        status="inconclusive",
        provider="not_called",
        model="none",
        mocked=False,
        cv_model_adapter=package.models.get("adapter", "unknown"),
        unassessed_candidates=[c.id for c in package.candidates],
        limitations=list(
            dict.fromkeys(
                package.limitations
                + [
                    "Physical identity and damage causation are not established",
                    "Shadows, reflections, hands, occlusion and mask leakage require human review",
                    "No conclusion about unseen surfaces; no automated financial action",
                ]
            )
        ),
    )
    pairs = supported_pairs(package)
    report.assessed_pairs = [(row.before_id, row.after_id) for row in pairs[: options.max_pairs]]
    if not pairs or package.outcome in ("inconclusive", "failed"):
        report.limitations.append("No adequately supported aligned pair; provider not invoked")
    elif package.metrics.get("candidates_truncated", 0):
        report.limitations.append(
            "Candidate artifact budget was exhausted; comparison is incomplete"
        )
    elif not package.candidates and any(
        note in package.limitations
        for note in ("boundary_without_appearance_support", "boundary_appearance_unassessable")
    ):
        report.limitations.append("Masks disagree without sufficient boundary appearance evidence")
    elif not package.candidates and package.boundary_changes:
        report.limitations.append(
            "Unassessed object boundary changes require human review; "
            "missing parts are not confirmed"
        )
    elif not package.candidates:
        report.status = "no_visible_change" if package.outcome == "comparable" else "partial"
        report.limitations.append(
            "No CV candidate in compared visible regions; not proof of no damage"
        )
    elif provider.kind == "disabled":
        report.error_code = "provider_unavailable"
    elif provider.kind in ("json_http", "gemini") and not options.allow_external:
        report.error_code = "external_processing_not_permitted"
    else:
        request, selected = None, []
        state = {}

        def verify(context):
            nonlocal request, selected
            try:
                request, selected = prepare(package, pairs, read_artifact, options)
                if not selected:
                    raise ProviderError("insufficient_evidence")
                report.selected_candidates = [c.id for c in selected]
                report.unassessed_candidates = [
                    c.id for c in package.candidates if c.id not in report.selected_candidates
                ]
                report.provider, report.model, report.mocked = (
                    provider.kind,
                    provider.model,
                    provider.mocked,
                )
                report.metrics.images_sent = len(request.images)
                report.metrics.image_bytes = sum(len(row["data"]) for row in request.images)
                report.metrics.attempts = 1
                try:
                    result = provider.send(request)
                except ProviderError:
                    raise
                except TimeoutError as exc:
                    raise ProviderError("provider_timeout") from exc
                except Exception as exc:
                    raise ProviderError("provider_failure") from exc
                report.metrics.attempts = result.attempts
                report.metrics.input_tokens = result.usage.input_tokens
                report.metrics.output_tokens = result.usage.output_tokens
                report.metrics.estimated_cost_usd = result.estimated_cost_usd
                state["reply"] = (
                    ProviderReply.model_validate_json(result.content)
                    if isinstance(result.content, str)
                    else ProviderReply.model_validate(result.content)
                )
                validate_reply(state["reply"], selected, request)
            except (ProviderError, ValueError, OSError) as exc:
                report.error_code = (
                    exc.code if isinstance(exc, ProviderError) else "provider_schema"
                )
                report.metrics.attempts = getattr(exc, "attempts", report.metrics.attempts)
                return StageResult(
                    stage="damage_verification",
                    evidence_ids=package.source_ids,
                    abstain=True,
                    limitations=[report.error_code],
                )
            return StageResult(
                stage="damage_verification",
                evidence_ids=package.source_ids,
                artifact_keys=[UUID(row["artifact_id"]) for row in request.images],
            )

        def fuse(context):
            report.findings = state["reply"].observations
            report.limitations.extend(state["reply"].limitations)
            repeated, conflicts = repeated_regions(selected, report.findings)
            if repeated:
                report.limitations.append(
                    "Overlapping observations in shared source frames are "
                    "not independent confirmations: " + ", ".join(sorted(map(str, repeated)))
                )
            if conflicts:
                report.limitations.append(
                    "Conflicting observations overlap in shared source frames; "
                    "all are retained for human review: " + ", ".join(sorted(map(str, conflicts)))
                )
            uncertain = bool(conflicts) or any(
                row.status == "insufficient_evidence" for row in report.findings
            )
            report.status = (
                "inconclusive"
                if uncertain
                else "partial"
                if report.unassessed_candidates or package.unmatched_ids
                else "human_review_required"
            )
            return StageResult(stage="evidence_fusion", evidence_ids=package.source_ids)

        def generate(context):
            return StageResult(
                stage="report_generation",
                evidence_ids=package.source_ids,
                limitations=["Human review required; provider claims are not physical proof"],
            )

        context = PipelineContext(
            inspection_id=package.inspection_id,
            reference_ids=list(dict.fromkeys(p.before_id for p in pairs)),
            return_ids=list(dict.fromkeys(p.after_id for p in pairs)),
        )
        result = Orchestrator(
            {"damage_verification": verify, "evidence_fusion": fuse, "report_generation": generate}
        ).run_assessment(context)
        report.stage_statuses = [row.stage for row in result.results]
    if package.boundary_changes:
        report.status = "inconclusive"
        report.limitations.append(
            "Boundary hypotheses remain unverified; no automated financial action"
        )
    report.metrics.elapsed_seconds = time.perf_counter() - started
    return AssessmentReport.model_validate(report.model_dump())
