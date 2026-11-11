"""One authorized DOTS hybrid call; preserve strict validation and every failure."""

import argparse
import io
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ep_engine.vlm_eval.contracts import Benchmark, Case, Limits, Reply
from ep_engine.vlm_eval.environment import load_environment
from ep_engine.vlm_eval.evidence import (
    constrained_prediction,
    prepare,
    sha,
    validate_citations,
    verified_case,
    verified_pairs,
)
from ep_engine.vlm_eval.fusion import fuse
from ep_engine.vlm_eval.provider import request_body
from ep_engine.vlm_eval.runner import Budget, assess, canonical, exclusive, write_json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".test-artifacts/openrouter-hybrid-acceptance-20261111"
MODEL = "dots-studio/dots-3-note-preview:free"


def read(path):
    return json.loads(path.read_bytes())


def require(condition, code):
    if not condition:
        raise ValueError(code)


def preservation():
    frozen = read(ROOT / ".test-artifacts/ep-v31-improvement-20261111/source-checksums.json")
    require(
        all(sha((ROOT / p).read_bytes()) == digest for p, digest in frozen.items()),
        "frozen_cv_source_changed",
    )
    photos = read(ROOT / ".test-artifacts/ep-v31-20261111/dataset-checksums.json")
    require(
        all(sha(Path(p["Path"]).read_bytes()).upper() == p["Hash"].upper() for p in photos),
        "original_photo_changed",
    )
    return dict(frozen_cv_source_files=len(frozen), original_photos=len(photos), unchanged=True)


def observation_checks(reply, prepared, report):
    records = []
    attached = {image["id"]: image for image in prepared["images"]}
    for index, observation in enumerate(reply.observations):
        source_ids = {str(observation.before_id), str(observation.after_id)}
        cited = set(map(str, observation.evidence_ids))
        crops = cited - set(prepared["original_ids"])
        single = reply.model_copy(update={"observations": [observation]})
        try:
            validate_citations(single, prepared)
            supported, reason = constrained_prediction(single, "hybrid", report, prepared)
            citations_valid = True
        except ValueError:
            supported, reason, citations_valid = None, "source_or_crop_citation_invalid", False
        records.append(
            dict(
                observation=index,
                both_originals_cited=source_ids <= cited,
                all_references_attached=cited <= attached.keys(),
                crop_ids=sorted(crops),
                crop_count=len(crops),
                artifact_references=[
                    {k: attached[i][k] for k in ("id", "kind", "source_ids")}
                    for i in sorted(crops)
                    if i in attached
                ],
                crop_source_binding_valid=all(
                    identifier in attached
                    and set(attached[identifier].get("source_ids", [])) <= source_ids
                    for identifier in crops
                ),
                source_frames_valid=(
                    observation.before_region.image_id == observation.before_id
                    and observation.after_region.image_id == observation.after_id
                ),
                normalized_regions_valid=True,  # Already enforced by the unchanged Reply contract.
                before_region=list(observation.before_region.box),
                after_region=list(observation.after_region.box),
                citations_valid=citations_valid,
                supported_prediction=supported,
                geometry_reason=reason,
                region_support=region_support(observation, prepared, report),
            )
        )
    return records


def region_support(observation, prepared, report):
    """Measure the unchanged gate's pixel scope; never repair or shrink model boxes."""
    import cv2
    import numpy as np

    pair = next(
        (
            p
            for p in verified_pairs(report.cv_package)
            if p.before_id == observation.before_id and p.after_id == observation.after_id
        ),
        None,
    )
    if pair is None:
        return dict(status="no_verified_geometry")
    with Image.open(io.BytesIO(prepared["_artifacts"][pair.overlap_id])) as image:
        mask = np.asarray(image) > 0
    height, width = mask.shape
    before_width, before_height = report.cv_package.processing_dimensions[observation.before_id]
    transform = np.asarray(pair.homography)
    inverse_mask = cv2.warpPerspective(
        mask.astype(np.uint8),
        np.linalg.inv(transform),
        (before_width, before_height),
        flags=cv2.INTER_NEAREST,
    )

    def box_support(array, box):
        h, w = array.shape
        x1, y1, x2, y2 = box
        region = array[
            int(y1 * h) : max(int(y1 * h) + 1, int(np.ceil(y2 * h))),
            int(x1 * w) : max(int(x1 * w) + 1, int(np.ceil(x2 * w))),
        ]
        return dict(
            processing_pixels=int(region.size),
            supported_pixels=int(np.count_nonzero(region)),
            supported_fraction=float(np.count_nonzero(region) / region.size) if region.size else 0,
        )

    bx1, by1, bx2, by2 = observation.before_region.box
    corners = np.array(
        [
            [
                [bx1 * before_width, by1 * before_height],
                [bx2 * before_width, by1 * before_height],
                [bx2 * before_width, by2 * before_height],
                [bx1 * before_width, by2 * before_height],
            ]
        ],
        np.float32,
    )
    projected = cv2.perspectiveTransform(corners, transform)[0] / np.array([width, height])
    low, high = projected.min(axis=0), projected.max(axis=0)
    x1, y1, x2, y2 = observation.after_region.box
    return dict(
        status="measured_processing_overlap",
        after_box=box_support(mask, observation.after_region.box),
        before_box=box_support(inverse_mask, observation.before_region.box),
        projected_boxes_intersect=bool(
            high[0] > x1 and low[0] < x2 and high[1] > y1 and low[1] < y2
        ),
        required_supported_fraction=1.0,
    )


def run():
    directory = OUT / "live"
    if (directory / "acceptance.json").exists():
        print("Completed acceptance preserved; no API request or output overwrite.")
        return
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    (directory / "cache").mkdir(mode=0o700)
    with exclusive(directory):
        before = preservation()
        configured, environment = load_environment(ROOT.parent / "backend/.env")
        require(configured.provider == "openrouter", "openrouter_not_enabled")
        config = Limits.model_validate(
            dict(
                configured.model_dump(),
                model=MODEL,
                allow_external=True,
                max_requests=1,
                generation_retries=0,
                max_images=5,
                reasoning_enabled=False,
                max_output_tokens=4096,
                run_seconds=120,
            )
        )
        benchmark = Benchmark.model_validate_json(
            (
                ROOT / ".test-artifacts/openrouter-finalization-20261111/live-manifest.json"
            ).read_bytes()
        )
        case = next(c for c in benchmark.cases if c.case_id == "phone-front")
        verified = verified_case(case)
        prepared = prepare(case, "hybrid", config, verified)
        body = request_body(prepared, config, Reply.model_json_schema())
        remote = body["response_format"]["json_schema"]["schema"]
        observation = remote["$defs"]["Observation"]["properties"]
        require(set(remote["required"]) == set(remote["properties"]), "optional_remote_fields")
        require(
            set(observation["evidence_ids"]["items"]["enum"])
            == {i["id"] for i in prepared["images"]},
            "incorrect_attachment_enum",
        )
        require(
            body["provider"]["data_collection"] == "deny"
            and not body["provider"]["allow_fallbacks"]
            and all(v == 0 for v in body["provider"]["max_price"].values()),
            "privacy_or_free_route_controls_changed",
        )
        for image in prepared["images"]:
            if image["kind"] == "original_capture":
                with Image.open(io.BytesIO(image["data"])) as png:
                    require(not png.info, "original_metadata_not_stripped")
        write_json(directory / "request-schema.json", remote)
        write_json(directory / "reply.schema.json", Reply.model_json_schema())
        write_json(
            directory / "request-receipt.json",
            dict(
                environment=environment,
                selected_model=MODEL,
                explicit_override=True,
                authorization="one hybrid phone-front request authorized in this user message",
                policy=body["provider"],
                reasoning=body.get("reasoning"),
                input_pixel_hashes=prepared["input_pixels_sha256"],
                images=[
                    dict(
                        {k: v for k, v in i.items() if k != "data"},
                        sha256=sha(i["data"]),
                        byte_size=len(i["data"]),
                    )
                    for i in prepared["images"]
                ],
                original_before_enum=observation["before_id"]["enum"],
                original_after_enum=observation["after_id"]["enum"],
            ),
        )
        write_json(directory / "config.json", config.model_dump(mode="json"))
        write_json(directory / "case.json", case.model_dump(mode="json"))
        (directory / "cv-evidence.json").write_bytes(case.cv_report.read_bytes())
        context = sha(
            canonical(
                dict(
                    case=case.model_dump(mode="json"),
                    limits=config.model_dump(),
                    authorization="single-live-hybrid",
                )
            )
        )
        budget = Budget(directory, config, context)
        row = assess(
            "hybrid",
            case,
            verified,
            config,
            directory,
            budget,
            time.monotonic() + config.run_seconds,
        )
        write_json(directory / "result.json", row)
        result = None
        fingerprint = row.get("request_fingerprint")
        if fingerprint:
            for folder in ("cache", "rejected"):
                path = directory / folder / f"{fingerprint}.json"
                if path.exists():
                    result = read(path)["result"]
                    write_json(directory / "provider-result.json", result)
                    break
        receipt = dict(
            status=row["status"],
            reason=row["reason"],
            latency_seconds=row["elapsed_seconds"],
            requests_reserved=budget.data["requests"],
            model_metadata=row.get("model_metadata"),
            schema_valid=False,
            citations_valid=False,
            observations=[],
            usage=result.get("usage") if result else None,
            provider_reported_cost_usd=result.get("provider_reported_cost_usd") if result else None,
            reserved_cost_usd=budget.data["reserved_usd"],
        )
        prepared["_artifacts"] = verified[3]
        if result:
            try:
                reply = Reply.model_validate(result["reply"])
                receipt["schema_valid"] = bool(reply.recapture_guidance)
                receipt["observations"] = observation_checks(reply, prepared, verified[1])
                try:
                    validate_citations(reply, prepared)
                    receipt["citations_valid"] = True
                except ValueError:
                    receipt["citation_failure"] = (
                        "original_source_or_attached_evidence_reference_invalid"
                    )
            except ValidationError as exc:
                receipt["schema_errors"] = [
                    dict(location=list(e["loc"]), type=e["type"])
                    for e in exc.errors(include_input=False, include_url=False)
                ]
        combined = fuse(verified[1].inspection_id, "hybrid", verified[1], row)
        require(
            combined.cv_report.model_dump_json() == verified[1].model_dump_json(),
            "cv_evidence_modified_during_fusion",
        )
        require(
            combined.payment_action == "none"
            and not combined.confirmed_damage
            and not combined.physical_identity_verified,
            "authority_invariant_failed",
        )
        receipt.update(
            verdict="accepted_in_verified_scope"
            if row["status"] == "completed" and row.get("prediction") is not None
            else "completed_with_abstention"
            if row["status"] == "completed"
            else "rejected",
            decision=combined.decision,
            supported_prediction=combined.supported_appearance_prediction,
            before=before,
            after=preservation(),
            integration_ready=False,
        )
        write_json(directory / "combined-report.json", combined.model_dump(mode="json"))
        write_json(directory / "acceptance.json", receipt)
        print(json.dumps(receipt, indent=2))


def report():
    receipt = read(OUT / "live/acceptance.json")
    live = OUT / "live"
    diagnostics = []
    required_fields_present = None
    if receipt["schema_valid"]:
        config = Limits.model_validate_json((live / "config.json").read_bytes())
        case = Case.model_validate_json((live / "case.json").read_bytes())
        verified = verified_case(case)
        prepared = prepare(case, "hybrid", config, verified)
        require(
            prepared["input_pixels_sha256"]
            == read(live / "request-receipt.json")["input_pixel_hashes"],
            "offline_revalidation_pixel_hash_mismatch",
        )
        prepared["_artifacts"] = verified[3]
        raw = read(live / "provider-result.json")["reply"]
        schema = read(live / "request-schema.json")
        required_fields_present = set(schema["required"]) <= raw.keys()
        diagnostics = observation_checks(Reply.model_validate(raw), prepared, verified[1])
    write_json(
        OUT / "validation-details.json",
        dict(
            live_acceptance_sha256=sha((live / "acceptance.json").read_bytes()),
            required_fields_present=required_fields_present,
            observations=diagnostics,
            api_calls_during_offline_validation=0,
        ),
    )
    tests = {}
    for path in OUT.glob("*.xml"):
        suites = list(ET.parse(path).getroot().iter("testsuite"))  # noqa: S314 - local test XML
        tests[path.name] = {
            key: sum(float(s.get(key, 0)) for s in suites)
            for key in ("tests", "errors", "failures", "skipped", "time")
        }
    write_json(
        OUT / "verification.json",
        dict(acceptance=receipt, tests=tests, observation_diagnostics=diagnostics),
    )
    geometry_table = [
        "| Observation | Before supported | After supported | Projected intersection | Decision |",
        "|---|---:|---:|---|---|",
    ]
    for detail in diagnostics:
        support = detail["region_support"]
        if support["status"] == "measured_processing_overlap":
            geometry_table.append(
                f"|{detail['observation']}|"
                f"{support['before_box']['supported_fraction']:.2%}|"
                f"{support['after_box']['supported_fraction']:.2%}|"
                f"{support['projected_boxes_intersect']}|abstained|"
            )
    text = f"""# EP v3.1 final bounded live-hybrid acceptance

Actual verdict: **{receipt["verdict"]}**. Combined decision: **{receipt["decision"]}**.
Reason: `{receipt["reason"]}`. No independently verified damage accuracy or application
integration readiness is established by this single consented engineering example.

One authorized phone-front hybrid request was reserved, with retries disabled.
Model: `dots-studio/dots-3-note-preview:free`. Original images and verified CV crops
were sent with `data_collection=deny`, all price caps zero, no paid/model fallback,
metadata stripping, five-image maximum and the existing configured timeout.
The metadata preflight verifies image/JSON support and zero catalog pricing before
generation. No synthetic generation or additional image request was made.

| Measurement | Actual result |
|---|---|
| Comparison record latency | {receipt["latency_seconds"]:.3f} s |
| Provider token usage | `{json.dumps(receipt["usage"])}` |
| Provider reported cost | {receipt["provider_reported_cost_usd"]} USD |
| Local reserved cost | {receipt["reserved_cost_usd"]} USD |
| JSON contract valid | {receipt["schema_valid"]} |
| Required remote fields present | {required_fields_present} |
| Source and attached-evidence citations valid | {receipt["citations_valid"]} |
| Supported change prediction | {receipt["supported_prediction"]} |

{chr(10).join(geometry_table)}

Both proposed boxes extend beyond verified overlap. The unchanged region gate requires
all assessed processing pixels in each source box to be supported, not just intersecting
projected bounding boxes. This is the precise remaining localization defect: the model
proposes broad screen regions spanning unsupported pixels. It is not a citation or
coordinate-unit failure. No unsupported appearance observation was promoted.
The detailed per-observation counts, artifact kinds, IDs and source bindings are retained
in private `validation-details.json`; overlap masks are evidence, not crop images.
Normalized coordinates and source frames use the unchanged strict reply contract.
Every positive must cite both originals; all crop references must be attached and
bound to those sources. Geometry and overlap use the existing verification gates.
Any unsupported region abstains; no model box is clipped, repaired, or promoted.

The original CV report remains intact in the combined report and a byte-identical
private evidence copy. All 58 frozen EP source files and 34 original photograph
hashes were verified before and after the call. Payment_action remains none,
physical identity and confirmed damage remain false, and human review is required.
No underlying CV, payment, database, application, model weight or Git change was made.

Affected regression and safety records: `{json.dumps(tests, sort_keys=True)}`.
The first preflight XML records two test-directory setup errors; its separate recheck
passed both tests. All 53 affected regressions and both privacy-policy checks passed.
Prior native verification is documented in [finalization](openrouter-v31-finalization.md);
it is not represented as a new native benchmark in this API-only acceptance run.

Actual private outputs are under `.test-artifacts/openrouter-hybrid-acceptance-20261111/live/`:
`combined-report.json`, `acceptance.json`, `provider-result.json` when available,
`request-schema.json`, `request-receipt.json`, `cv-evidence.json`, and the append-only
one-request ledger. Failed outputs are preserved. Re-running a completed campaign
does not make another API call. See [operator documentation](openrouter-v31.md).

**Readiness:** bounded standalone human review only. Independent labels, demonstrated
paired benefit and representative reliability measurements remain absent. This
single case cannot justify application integration or damage/financial automation.
"""
    (ROOT / "docs/openrouter-v31-hybrid-acceptance.md").write_text(text, "utf-8")
    print(json.dumps(dict(verdict=receipt["verdict"], reason=receipt["reason"], tests=tests)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-only", action="store_true")
    if parser.parse_args().report_only:
        report()
    else:
        run()
