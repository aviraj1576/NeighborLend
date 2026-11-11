"""Opt-in private-response replay; no inference or network access is permitted."""

import io
import json
import os
import socket

import numpy as np
import pytest
from PIL import Image
from test_vlm_evaluation import case as case
from test_vlm_evaluation import positive

from ep_engine.vlm_eval.contracts import Limits
from ep_engine.vlm_eval.evidence import (
    constrained_prediction,
    prepare,
    sha,
    validate_citations,
    verified_case,
)
from ep_engine.vlm_eval.fusion import fuse
from scripts.audit_hybrid_overlap import LIVE, load_snapshot, measure


@pytest.fixture
def snapshot(monkeypatch):
    if os.environ.get("EP_RUN_HYBRID_REPLAY") != "1":
        pytest.skip("Private preserved capture replay requires EP_RUN_HYBRID_REPLAY=1")

    def forbidden(*args, **kwargs):
        pytest.fail("Preserved-response regression attempted network/provider execution")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr("ep_engine.vlm_eval.runner.LiveCall", forbidden)
    return load_snapshot()


@pytest.mark.parametrize("index", [0, 1])
def test_live_observation_still_abstains_without_mutation(snapshot, index):
    reply, verified, prepared = snapshot
    frozen = reply.model_dump_json(), verified[1].model_dump_json()
    single = reply.model_copy(update={"observations": [reply.observations[index]]})
    validate_citations(single, prepared)
    assert constrained_prediction(single, "hybrid", verified[1], prepared) == (
        None,
        "claimed_region_outside_verified_overlap",
    )
    assert (reply.model_dump_json(), verified[1].model_dump_json()) == frozen


def test_saved_masks_and_exact_unsupported_pixel_counts(snapshot):
    diagnostics, _ = measure(*snapshot)
    assert diagnostics["reconstructed_mask_differing_pixels"] == 0
    assert diagnostics["mask_shape"] == [347, 768]
    for row in diagnostics["observations"]:
        assert row["before"]["raster_box"] == [135, 145, 342, 523]
        assert row["before"]["pixels"] == 78246
        assert row["before"]["unsupported_pixels"] == 18004
        assert row["after"]["raster_box"] == [238, 111, 576, 275]
        assert row["after"]["pixels"] == 55432
        assert row["after"]["unsupported_pixels"] == 11071
        assert row["after_raw_overlap"]["unsupported_pixels"] == 7260
        assert row["after_segmentation"]["unsupported_pixels"] == 6985


def test_original_coordinate_mapping_and_homography_direction(snapshot):
    diagnostics, _ = measure(*snapshot)
    for row in diagnostics["observations"]:
        assert row["before_original_pixels"] == pytest.approx([282.36, 304, 709.52, 1088])
        assert row["after_original_pixels"] == pytest.approx([577.84, 269.76, 1398, 665.97])
        assert row["roundtrip_max_processing_error"] < 1e-9
        assert row["source_mapping_max_processing_error"] < 1e-9
        # Intersection alone cannot replace full source-box support.
        assert row["projected_boxes_intersect"]
        assert row["prediction"] is None


def test_request_receipt_and_attached_crop_pixel_mapping(snapshot):
    reply, verified, prepared = snapshot
    receipt = json.loads((LIVE / "request-receipt.json").read_bytes())
    assert prepared["input_pixels_sha256"] == receipt["input_pixel_hashes"]
    for image, saved in zip(prepared["images"], receipt["images"], strict=True):
        assert image["id"] == saved["id"]
        assert sha(image["data"]) == saved["sha256"]
        assert (image["width"], image["height"]) == (saved["width"], saved["height"])
        if image["kind"] not in {"before_crop", "after_crop"}:
            continue
        identifier = next(k for k in verified[3] if str(k) == image["id"])
        candidate = next(
            c for c in verified[1].cv_package.candidates if identifier in c.artifact_ids
        )
        stage = image["kind"].removesuffix("_crop")
        source = next(r for r in verified[2] if r.stage == stage)
        box = getattr(candidate, f"{stage}_box")
        h, w = source.rgb.shape[:2]
        x, y = int(box.x1 * w), int(box.y1 * h)
        expected = source.rgb[y : y + image["height"], x : x + image["width"]]
        with Image.open(io.BytesIO(image["data"])) as crop:
            assert np.array_equal(expected, np.asarray(crop))
        assert image["source_ids"] == [str(source.id)]
    validate_citations(reply, prepared)


def test_full_replay_preserves_uncertain_fusion_and_live_bytes(snapshot):
    frozen = {p: sha(p.read_bytes()) for p in LIVE.rglob("*") if p.is_file()}
    reply, verified, prepared = snapshot
    prediction, reason = constrained_prediction(reply, "hybrid", verified[1], prepared)
    result = fuse(
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
    assert result.decision == "uncertain"
    assert result.supported_appearance_prediction is None
    assert result.vlm_appearance_opinion is True
    assert not result.confirmed_damage and not result.physical_identity_verified
    assert result.payment_action == "none" and result.human_review_required
    assert all(sha(p.read_bytes()) == digest for p, digest in frozen.items())


@pytest.mark.parametrize(
    "stage,reason",
    [
        ("before", "claimed_reference_outside_verified_overlap"),
        ("after", "claimed_region_outside_verified_overlap"),
    ],
)
def test_either_source_requires_full_support(case, stage, reason):
    # Generated controls, never a repaired/clipped version of a live observation.
    verified = verified_case(case)
    prepared = prepare(case, "hybrid", Limits(), verified)
    prepared["_artifacts"] = verified[3]
    reply = positive(verified)
    getattr(reply.observations[0], f"{stage}_region").box = (0, 0, 0.1, 0.1)
    assert constrained_prediction(reply, "hybrid", verified[1], prepared) == (None, reason)
