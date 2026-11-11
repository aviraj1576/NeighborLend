"""Replay preserved hybrid evidence offline; never call a provider or alter live outputs."""

import argparse
import io
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ep_engine.vlm_eval.contracts import Case, Limits, Reply
from ep_engine.vlm_eval.evidence import (
    constrained_prediction,
    prepare,
    sha,
    verified_case,
    verified_pairs,
)
from ep_engine.vlm_eval.fusion import fuse

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / ".test-artifacts/openrouter-hybrid-acceptance-20261111/live"


def deny_network(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
        raise RuntimeError("Offline audit forbids networking and child processes")


def load_snapshot(live=LIVE):
    case = Case.model_validate_json((live / "case.json").read_bytes())
    verified = verified_case(case)  # Verifies source and artifact hashes; no inference.
    prepared = prepare(case, "hybrid", Limits(max_images=5), verified)
    prepared["_artifacts"] = verified[3]
    reply = Reply.model_validate_json(
        json.dumps(json.loads((live / "provider-result.json").read_bytes())["reply"])
    )
    return reply, verified, prepared


def decode(data):
    with Image.open(io.BytesIO(data)) as image:
        return np.asarray(image).copy() > 0


def bounds(box, size):
    return (np.asarray(box) * np.asarray([*size, *size])).tolist()


def support(mask, box):
    height, width = mask.shape
    x1, y1, x2, y2 = bounds(box, (width, height))
    x1, y1 = int(x1), int(y1)
    x2, y2 = max(x1 + 1, int(np.ceil(x2))), max(y1 + 1, int(np.ceil(y2)))
    region = mask[y1:y2, x1:x2]
    supported = int(np.count_nonzero(region))
    return dict(
        raster_box=[x1, y1, x2, y2],
        pixels=int(region.size),
        supported_pixels=supported,
        unsupported_pixels=int(region.size) - supported,
        supported_fraction=supported / region.size if region.size else 0,
    )


def measure(reply, verified, prepared):
    report, artifacts = verified[1], verified[3]
    (pair,) = verified_pairs(report.cv_package)
    package = report.cv_package
    before, after = pair.before_id, pair.after_id
    bw, bh = package.processing_dimensions[before]
    aw, ah = package.processing_dimensions[after]
    matrix = np.asarray(pair.homography)
    mask = decode(artifacts[pair.overlap_id])
    segments = {s.evidence_id: decode(artifacts[s.mask_id]) for s in package.segmentation}
    warped = cv2.warpPerspective(
        segments[before].astype(np.uint8), matrix, (aw, ah), flags=cv2.INTER_NEAREST
    ).astype(bool)
    raw = warped & segments[after]
    rebuilt = cv2.erode(raw.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    reference = cv2.warpPerspective(
        mask.astype(np.uint8), np.linalg.inv(matrix), (bw, bh), flags=cv2.INTER_NEAREST
    ).astype(bool)
    rows = []
    for observation in reply.observations:
        single = reply.model_copy(update={"observations": [observation]})
        prediction, reason = constrained_prediction(single, "hybrid", report, prepared)
        bx1, by1, bx2, by2 = bounds(observation.before_region.box, (bw, bh))
        corners = np.array([[bx1, by1], [bx2, by1], [bx2, by2], [bx1, by2]])
        projected = cv2.perspectiveTransform(corners[None], matrix)[0]
        normalized = projected / [aw, ah]
        low, high = normalized.min(axis=0), normalized.max(axis=0)
        ax1, ay1, ax2, ay2 = observation.after_region.box
        reverse = cv2.perspectiveTransform(projected[None], np.linalg.inv(matrix))[0]
        source_scale = np.diag(
            [
                bw / package.source_dimensions[before][0],
                bh / package.source_dimensions[before][1],
                1.0,
            ]
        )
        target_scale = np.diag(
            [
                aw / package.source_dimensions[after][0],
                ah / package.source_dimensions[after][1],
                1.0,
            ]
        )
        source_matrix = np.linalg.inv(target_scale) @ matrix @ source_scale
        original = corners / [source_scale[0, 0], source_scale[1, 1]]
        via_source = cv2.perspectiveTransform(original[None], source_matrix)[0]
        rows.append(
            dict(
                prediction=prediction,
                reason=reason,
                before_normalized=list(observation.before_region.box),
                after_normalized=list(observation.after_region.box),
                before_original_pixels=bounds(
                    observation.before_region.box, package.source_dimensions[before]
                ),
                after_original_pixels=bounds(
                    observation.after_region.box, package.source_dimensions[after]
                ),
                before=support(reference, observation.before_region.box),
                after=support(mask, observation.after_region.box),
                after_raw_overlap=support(raw, observation.after_region.box),
                after_segmentation=support(segments[after], observation.after_region.box),
                before_segmentation=support(segments[before], observation.before_region.box),
                projected_after_normalized=normalized.tolist(),
                projected_boxes_intersect=bool(
                    high[0] > ax1 and low[0] < ax2 and high[1] > ay1 and low[1] < ay2
                ),
                roundtrip_max_processing_error=float(np.max(np.abs(reverse - corners))),
                source_mapping_max_processing_error=float(
                    np.max(
                        np.abs(via_source * [target_scale[0, 0], target_scale[1, 1]] - projected)
                    )
                ),
            )
        )
    return dict(
        source_dimensions={str(k): v for k, v in package.source_dimensions.items()},
        processing_dimensions={str(k): v for k, v in package.processing_dimensions.items()},
        homography_before_processing_to_after_processing=pair.homography,
        mask_shape=list(mask.shape),
        overlap_id=str(pair.overlap_id),
        reconstructed_mask_differing_pixels=int(np.count_nonzero(mask != rebuilt)),
        observations=rows,
    ), (reference, mask)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.addaudithook(deny_network)
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / ".test-artifacts") or output.is_relative_to(LIVE):
        raise ValueError("Write only to a separate EP test-artifact directory")
    output.mkdir(parents=True, exist_ok=True)
    frozen = {p: sha(p.read_bytes()) for p in LIVE.rglob("*") if p.is_file()}
    reply, verified, prepared = load_snapshot()
    result, masks = measure(reply, verified, prepared)
    receipt = json.loads((LIVE / "request-receipt.json").read_bytes())
    result["request_images_match_preserved_receipt"] = all(
        {k: v for k, v in image.items() if k != "data"}
        == {k: v for k, v in saved.items() if k not in {"sha256", "byte_size"}}
        and sha(image["data"]) == saved["sha256"]
        for image, saved in zip(prepared["images"], receipt["images"], strict=True)
    )
    prediction, reason = constrained_prediction(reply, "hybrid", verified[1], prepared)
    combined = fuse(
        verified[1].inspection_id,
        "hybrid",
        verified[1],
        dict(
            status="completed",
            reason=reason,
            prediction=prediction,
            reply=reply.model_dump(mode="json"),
        ),
    )
    result.update(
        decision=combined.decision,
        supported_prediction=prediction,
        reason=reason,
        network_calls=0,
        provider_or_model_execution=False,
    )
    for row, mask in zip(verified[2], masks, strict=True):
        rgb = row.rgb.copy()
        rgb[mask] = (0.55 * rgb[mask] + 0.45 * np.array([0, 255, 0])).astype(np.uint8)
        image = Image.fromarray(rgb)
        draw = ImageDraw.Draw(image)
        box = getattr(reply.observations[0], f"{row.stage}_region").box
        draw.rectangle(bounds(box, image.size), outline="red", width=2)
        draw.text(
            (5, 5),
            f"{row.stage}: green=verified support; red=both unchanged VLM boxes",
            fill="white",
            stroke_width=1,
            stroke_fill="black",
        )
        image.save(output / f"{row.stage}-overlap.png")
    result["preserved_live_files_unchanged"] = all(
        sha(p.read_bytes()) == digest for p, digest in frozen.items()
    )
    result["preserved_live_sha256"] = {str(p.relative_to(LIVE)): d for p, d in frozen.items()}
    (output / "diagnostics.json").write_text(json.dumps(result, indent=2) + "\n", "utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
