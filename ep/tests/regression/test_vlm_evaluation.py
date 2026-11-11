"""Transport/safety/evaluation software controls; no real VLM accuracy claims."""

import io
import json
import time
from uuid import uuid4

import httpx
import numpy as np
import pytest
from PIL import Image, PngImagePlugin
from pydantic import ValidationError

from ep_engine.cv.pipeline import InputImage
from ep_engine.schemas.models import Box
from ep_engine.v3.config import V3Config
from ep_engine.v31.api import inspect_inputs
from ep_engine.vlm_eval.contracts import Benchmark, Case, IndependentLabel, Limits, Reply
from ep_engine.vlm_eval.evidence import (
    constrained_prediction,
    prepare,
    sha,
    validate_citations,
    verified_case,
)
from ep_engine.vlm_eval.provider import EvaluationError, Gemini, LiveCall, request_body
from ep_engine.vlm_eval.runner import Budget, cache_key, run, summarize


class Models:
    def segment(self, rgb, box):
        mask = np.zeros(rgb.shape[:2], bool)
        mask[20:-20, 20:-20] = True
        return mask

    def embedding(self, *args):
        return np.ones(384, np.float32)

    def close(self):
        pass

    def metrics(self):
        return {}


@pytest.fixture
def case(tmp_path):
    pixels = np.random.default_rng(817).integers(30, 200, (256, 256, 3), np.uint8)
    rows = []
    evidence = []
    config = V3Config(device="cpu", appearance_backend="opencv")
    for stage in ("before", "after"):
        identifier = uuid4()
        path = tmp_path / f"{identifier}.png"
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("private", "GPS-private-address")
        Image.fromarray(pixels).save(path, pnginfo=metadata)
        digest = sha(path.read_bytes())
        target = Box(x1=0.05, y1=0.05, x2=0.95, y2=0.95)
        rows.append(
            InputImage(
                identifier,
                stage,
                pixels.copy(),
                digest,
                target,
                original_size=(256, 256),
                original_rgb=pixels.copy(),
            )
        )
        evidence.append(
            dict(
                id=str(identifier),
                stage=stage,
                path=str(path),
                sha256=digest,
                normalized_sha256=digest,
                target=target.model_dump(mode="json"),
            )
        )
    identifier = uuid4()
    request = tmp_path / "input.json"
    request.write_text(
        json.dumps(
            dict(
                inspection_id=str(identifier),
                config=config.model_dump(mode="json"),
                evidence=evidence,
            )
        )
    )
    report = inspect_inputs(
        identifier,
        rows,
        tmp_path / "artifacts",
        config,
        models=Models(),
        surface_observation_budget=0,
    )
    output = tmp_path / "report.json"
    output.write_text(report.model_dump_json())
    return Case(
        case_id="generated",
        input_manifest=request,
        input_sha256=sha(request.read_bytes()),
        cv_report=output,
        cv_sha256=sha(output.read_bytes()),
        object_group="test-fixture",
        kind="synthetic",
        split="software_control",
        provenance="Generated pixels for deterministic software tests only",
    )


def positive(verified):
    before, after = verified[2]
    return Reply(
        change="visible_difference",
        uncertainty=["Physical cause is unknown"],
        observations=[
            dict(
                before_id=before.id,
                after_id=after.id,
                before_region=dict(image_id=before.id, box=[0.3, 0.3, 0.5, 0.5]),
                after_region=dict(image_id=after.id, box=[0.3, 0.3, 0.5, 0.5]),
                before_visible="Smooth area",
                after_visible="Darker line",
                explanation="Visible line differs",
                alternatives=["Lighting or registration"],
                evidence_ids=[before.id, after.id],
            )
        ],
    )


def test_verified_originals_metadata_removed_and_label_blind(case):
    verified = verified_case(case)
    prepared = prepare(case, "vlm_only", Limits(), verified)
    assert "cv" not in prepared["evidence"]
    assert "generated" not in json.dumps(prepared["evidence"])
    for image in prepared["images"]:
        with Image.open(io.BytesIO(image["data"])) as decoded:
            assert not decoded.info
            assert decoded.size == (256, 256)
            assert np.array_equal(np.asarray(decoded), verified[2][0].original_rgb)
    labeled = case.model_copy(
        update={
            "label": IndependentLabel(
                status="independently_reviewed",
                task="visible_appearance_change",
                change_present=False,
                reviewer="software-fixture",
                basis="Generated identical-pixel test, not real condition truth",
                annotation_version="1",
            )
        }
    )
    other = prepare(labeled, "vlm_only", Limits(), verified)
    assert cache_key(prepared, "vlm_only", Limits(), case) == cache_key(
        other, "vlm_only", Limits(), labeled
    )


def test_cv_artifact_and_source_tampering_fails_before_any_model(case):
    package = verified_case(case)[1].cv_package
    path = case.cv_report.parent / "artifacts" / f"{package.artifacts[0].id}.png"
    path.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="digest"):
        verified_case(case)


@pytest.mark.parametrize(
    "field,value",
    [("payment_action", "release"), ("physical_identity_verified", True), ("extra", "claim")],
)
def test_reply_has_no_financial_or_identity_authority(field, value):
    payload = Reply(change="uncertain", uncertainty=["Unknown"]).model_dump()
    payload[field] = value
    with pytest.raises(ValidationError):
        Reply.model_validate(payload)


def test_observations_require_grounded_source_citations(case):
    verified = verified_case(case)
    prepared = prepare(case, "vlm_only", Limits(), verified)
    reply = positive(verified)
    validate_citations(reply, prepared)
    reply.observations[0].evidence_ids.append(uuid4())
    with pytest.raises(ValueError, match="ungrounded"):
        validate_citations(reply, prepared)


def test_hybrid_cannot_override_geometry_or_claim_outside_overlap(case):
    verified = verified_case(case)
    prepared = prepare(case, "hybrid", Limits(), verified)
    prepared["_artifacts"] = verified[3]
    reply = positive(verified)
    assert constrained_prediction(reply, "hybrid", verified[1], prepared)[1] == (
        "cv_vlm_disagreement_requires_human_review"
    )
    reply.observations[0].after_region.box = (0.0, 0.0, 0.1, 0.1)
    assert constrained_prediction(reply, "hybrid", verified[1], prepared)[0] is None
    verified[1].cv_package.pairs[0].status = "inconclusive"
    assert constrained_prediction(positive(verified), "hybrid", verified[1], prepared)[0] is None
    # The VLM-only arm remains an explicitly unverified interpretation.
    assert constrained_prediction(positive(verified), "vlm_only", verified[1], prepared)[0] is True


def test_hybrid_negative_cannot_erase_cv_positive(case):
    verified = verified_case(case)
    prepared = prepare(case, "hybrid", Limits(), verified)
    prepared["_artifacts"] = verified[3]
    verified[1].cv_package.outcome = "partially_comparable"
    reply = Reply(change="no_visible_difference", uncertainty=["Only some surfaces are visible"])
    assert constrained_prediction(reply, "hybrid", verified[1], prepared)[0] is None


def test_budget_persisted_before_send_and_never_refunds(tmp_path):
    limits = Limits(
        max_requests=1, max_cost_usd=0.1, input_usd_per_million=1, output_usd_per_million=2
    )
    budget = Budget(tmp_path, limits, "scope")
    budget.reserve("first")
    assert json.loads((tmp_path / "budget.json").read_bytes())["requests"] == 1
    with pytest.raises(EvaluationError, match="request_budget"):
        Budget(tmp_path, limits, "scope").reserve("retry-after-timeout")
    with pytest.raises(ValueError, match="different"):
        Budget(tmp_path, limits, "another")


def test_no_network_without_explicit_rates_or_sufficient_cost_budget(tmp_path):
    with pytest.raises(EvaluationError, match="prices_required"):
        Budget(tmp_path, Limits(), "a").reserve("x")
    limits = Limits(max_cost_usd=0, input_usd_per_million=1, output_usd_per_million=1)
    with pytest.raises(EvaluationError, match="cost_budget"):
        Budget(tmp_path, limits, "a").reserve("x")
    assert json.loads((tmp_path / "budget.json").read_bytes())["requests"] == 0
    assert not (tmp_path / "budget.jsonl").exists()


def test_gemini_transport_fixed_host_inline_originals_no_secrets_in_body(case):
    limits = Limits(provider="gemini", model="gemini-test", allow_external=True)
    prepared = prepare(case, "vlm_only", limits, verified_case(case))
    body = request_body(prepared, limits, Reply.model_json_schema())
    seen = []

    def transport(request):
        seen.append(request)
        assert request.url.host == "generativelanguage.googleapis.com"
        assert not request.url.query
        assert request.headers["x-goog-api-key"] == "private-test-key"
        assert b"private-test-key" not in request.content
        assert b"GPS-private-address" not in request.content
        return httpx.Response(200, json={"totalTokens": 123})

    provider = Gemini(limits, "private-test-key", httpx.MockTransport(transport))
    assert provider.count(body) == 123 and len(seen) == 1


@pytest.mark.parametrize(
    "response,code",
    [
        (httpx.Response(302, headers={"location": "https://example.com"}), "provider_rejected"),
        (httpx.Response(200, content=b"x" * 262145), "response_too_large"),
        (httpx.Response(200, json={"totalTokens": True}), "input_token_limit"),
    ],
)
def test_bounded_transport_rejects_redirect_oversize_and_bad_usage(response, code):
    provider = Gemini(
        Limits(provider="gemini", model="gemini-test", allow_external=True),
        "secret",
        httpx.MockTransport(lambda _: response),
    )
    with pytest.raises(EvaluationError, match=code):
        provider.count({})


def test_provider_timeout_errors_never_include_secret():
    def transport(request):
        raise httpx.ReadTimeout("private-test-key raw response")

    provider = Gemini(
        Limits(provider="gemini", model="gemini-test", allow_external=True),
        "private-test-key",
        httpx.MockTransport(transport),
    )
    with pytest.raises(EvaluationError) as error:
        provider.count({})
    assert "private-test-key" not in str(error.value)


def test_offline_run_cache_and_metrics_are_not_vlm_accuracy(case, tmp_path):
    directory = tmp_path / "experiment"
    benchmark = Benchmark(cases=[case])
    first = run(benchmark, Limits(provider="offline_fixture"), directory)
    second = run(benchmark, Limits(provider="offline_fixture"), directory)
    assert first["arms"] == 3
    assert second["modes"]["vlm_only"]["cache_hits"] == 1
    assert first["modes"]["cv_only"]["metrics"]["software_control"]["status"] == "blocked_no_labels"
    assert first["physical_damage_accuracy"] is None
    assert not first["credential_available"]
    assert "NOT JUSTIFIED" in first["integration_recommendation"]


def test_independent_labels_only_and_abstentions_not_silent_negatives(case):
    label = IndependentLabel(
        status="independently_reviewed",
        task="visible_appearance_change",
        change_present=True,
        reviewer="generated-test",
        basis="Known generated edit used solely to check metric arithmetic",
        annotation_version="1",
    )
    labeled = case.model_copy(update={"label": label})
    benchmark = Benchmark(cases=[labeled])
    rows = [
        dict(case_id=case.case_id, mode=m, status="completed", prediction=None, cache_hit=False)
        for m in ("cv_only", "vlm_only", "hybrid")
    ]
    report = summarize(benchmark, rows)
    for mode in report["modes"].values():
        metrics = mode["metrics"]["software_control"]
        assert metrics["labelled"] == 1 and metrics["assessed"] == 0
        assert metrics["abstention_rate"] == 1
        assert metrics["recall_lower_bound_including_abstentions"] == 0
        assert metrics["precision"] is None


def test_split_leakage_and_unknown_truth_rejected(case):
    other = case.model_copy(update={"case_id": "other", "split": "test"})
    with pytest.raises(ValidationError, match="crosses splits"):
        Benchmark(cases=[case, other])
    with pytest.raises(ValidationError):
        IndependentLabel(
            status="model_generated",
            task="visible_appearance_change",
            change_present=True,
            reviewer="x",
            basis="Cannot be independent model-generated truth",
            annotation_version="1",
        )


def test_call_worker_hard_deadline_terminates_process():
    # No credentials: even an expensive child import cannot exceed this wall bound.
    limits = Limits(
        provider="gemini", model="gemini-test", allow_external=True, request_seconds=0.1
    )
    started = time.monotonic()
    call = LiveCall(limits, {})
    try:
        with pytest.raises(EvaluationError):
            call.receive()
    finally:
        call.close()
    assert time.monotonic() - started < 8


def test_durable_ledger_survives_a_failed_diagnostic_snapshot(tmp_path, monkeypatch):
    import ep_engine.vlm_eval.runner as runner

    limits = Limits(max_requests=1, input_usd_per_million=1, output_usd_per_million=1)
    budget = Budget(tmp_path, limits, "same-run")
    original = runner.write_json
    monkeypatch.setattr(
        runner,
        "write_json",
        lambda *args: (_ for _ in ()).throw(PermissionError("Windows sharing refusal")),
    )
    with pytest.raises(PermissionError):
        budget.reserve("possibly-billed")
    monkeypatch.setattr(runner, "write_json", original)
    with pytest.raises(EvaluationError, match="request_budget"):
        Budget(tmp_path, limits, "same-run").reserve("must-not-reset")


def test_torn_reservation_ledger_fails_closed(tmp_path):
    limits = Limits(input_usd_per_million=1, output_usd_per_million=1)
    budget = Budget(tmp_path, limits, "same-run")
    budget.reserve("first")
    with (tmp_path / "budget.jsonl").open("ab") as stream:
        stream.write(b'{"interrupted":')
    with pytest.raises(ValueError):
        Budget(tmp_path, limits, "same-run")


def test_positive_metrics_are_measured_only_on_reviewed_appearance_truth(case):
    labeled = case.model_copy(
        update={
            "label": IndependentLabel(
                status="independently_reviewed",
                task="visible_appearance_change",
                change_present=True,
                reviewer="software-fixture",
                basis="Synthetic label to verify confusion-count arithmetic only",
                annotation_version="1",
            )
        }
    )
    rows = [
        dict(case_id=case.case_id, mode=m, status="completed", prediction=True, cache_hit=False)
        for m in ("cv_only", "vlm_only", "hybrid")
    ]
    result = summarize(Benchmark(cases=[labeled]), rows)
    assert result["paired_completed_independently_labeled_cases"] == 1
    assert result["modes"]["hybrid"]["metrics"]["software_control"]["tp"] == 1
    assert result["modes"]["hybrid"]["metrics"]["software_control"]["recall"] == 1
    assert result["modes"]["hybrid"]["metrics"]["test"]["status"] == "blocked_no_labels"
    assert result["physical_damage_accuracy"] is None


def test_simulated_live_roundtrip_usage_and_cached_result_revalidation(case, tmp_path, monkeypatch):
    import ep_engine.vlm_eval.runner as runner

    verified = verified_case(case)
    reply = positive(verified).model_dump(mode="json")
    calls = []

    class SimulatedCall:
        def __init__(self, *args):
            calls.append(1)
            self.index = 0

        def receive(self):
            self.index += 1
            return (
                {"count": 123}
                if self.index == 1
                else dict(
                    reply=reply,
                    usage={
                        "promptTokenCount": 123,
                        "candidatesTokenCount": 35,
                        "thoughtsTokenCount": 5,
                    },
                )
            )

        def proceed(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(runner, "LiveCall", SimulatedCall)
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-credential-only")
    limits = Limits(
        provider="gemini",
        model="gemini-software-fixture",
        allow_external=True,
        free_only=False,
        input_usd_per_million=1,
        output_usd_per_million=2,
    )
    directory = tmp_path / "simulated"
    (directory / "cache").mkdir(parents=True)
    budget = Budget(directory, limits, "simulation")
    result = runner.assess(
        "hybrid", case, verified, limits, directory, budget, time.monotonic() + 30
    )
    assert result["status"] == "completed" and result["prediction"] is None
    assert result["reason"] == "cv_vlm_disagreement_requires_human_review"
    assert result["estimated_cost_usd"] == pytest.approx((123 + 40 * 2) / 1e6)
    again = runner.assess(
        "hybrid", case, verified, limits, directory, budget, time.monotonic() + 30
    )
    assert again["cache_hit"] and len(calls) == 1 and budget.data["requests"] == 1
    # Cache is untrusted input too: digest changes cannot reuse billed output.
    path = next((directory / "cache").glob("*.json"))
    content = json.loads(path.read_bytes())
    content["result"]["reply"]["physical_identity_verified"] = True
    path.write_text(json.dumps(content))
    invalid = runner.assess(
        "hybrid", case, verified, limits, directory, budget, time.monotonic() + 30
    )
    assert invalid["status"] == "failed" and invalid["reason"] == "cache_integrity"


def test_before_region_and_pairwise_support_cannot_be_forged(case):
    verified = verified_case(case)
    prepared = prepare(case, "hybrid", Limits(), verified)
    prepared["_artifacts"] = verified[3]
    reply = positive(verified)
    reply.observations[0].before_region.box = (0.0, 0.0, 0.1, 0.1)
    assert constrained_prediction(reply, "hybrid", verified[1], prepared)[0] is None
    reply = positive(verified)
    reply.observations[0].before_region.box = (0.6, 0.6, 0.7, 0.7)
    assert (
        constrained_prediction(reply, "hybrid", verified[1], prepared)[1]
        == "claimed_regions_do_not_correspond_geometrically"
    )
    verified[1].cv_package.pairs[0].source_coverage = 0.001
    assert constrained_prediction(positive(verified), "hybrid", verified[1], prepared)[0] is None


def test_free_only_blocks_unconfirmed_or_nonzero_pricing(case, tmp_path, monkeypatch):
    import ep_engine.vlm_eval.runner as runner

    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key-never-sent")

    def forbidden(*args):
        pytest.fail("Free-only guard must reject before any network call")

    monkeypatch.setattr(runner, "LiveCall", forbidden)
    limits = Limits(provider="gemini", model="gemini-test", allow_external=True)
    budget = Budget(tmp_path, limits, "free-guard")
    result = runner.assess(
        "vlm_only", case, verified_case(case), limits, tmp_path, budget, time.monotonic() + 10
    )
    assert result["reason"] == "free_tier_billing_confirmation_required"
    assert budget.data["requests"] == 0


def test_explicit_key_file_is_not_executed_and_accepts_opaque_keys(tmp_path, monkeypatch):
    from scripts.evaluate_vlm import load_key_file

    path = tmp_path / "key.env"
    key = "synthetic.key-with-dots_and_symbols=1234"
    path.write_text('UNRELATED=do-not-load\nGEMINI_API_KEY="' + key + '"\n')
    monkeypatch.delenv("UNRELATED", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder-for-test-cleanup")
    load_key_file(path)
    import os

    assert os.environ["GEMINI_API_KEY"] == key
    assert "UNRELATED" not in os.environ


def test_coordinate_units_and_compact_provider_schema():
    from ep_engine.vlm_eval.provider import response_schema

    original = Reply.model_json_schema()
    coordinates = original["$defs"]["Region"]["properties"]["box"]["prefixItems"]
    assert len(coordinates) == 4
    assert all(c["minimum"] == 0 and c["maximum"] == 1 for c in coordinates)
    remote = response_schema(original)
    box = remote["$defs"]["Region"]["properties"]["box"]
    assert box["minItems"] == box["maxItems"] == 4
    assert box["items"] == {"type": "number", "minimum": 0, "maximum": 1}
    assert "maxItems" not in remote["properties"]["observations"]
    assert original["properties"]["observations"]["maxItems"] == 8
    with pytest.raises(ValidationError):
        Reply(change="uncertain", observations=[], uncertainty=["unknown"] * 13)


def test_hybrid_rejected_geometry_can_retain_unverified_opinion(case, tmp_path, monkeypatch):
    import ep_engine.vlm_eval.runner as runner

    verified = verified_case(case)
    verified[1].cv_package.pairs[0].status = "inconclusive"
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key-never-sent")

    observed = []
    reply = positive(verified)
    reply.recapture_guidance = ["Capture matching surfaces"]

    class Call:
        def __init__(self, config, body):
            observed.append(body)
            self.reads = 0

        def receive(self):
            self.reads += 1
            return (
                {"count": 100}
                if self.reads == 1
                else dict(
                    reply=reply.model_dump(mode="json"),
                    usage={},
                )
            )

        def proceed(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(runner, "LiveCall", Call)
    limits = Limits(
        provider="gemini",
        model="gemini-test",
        allow_external=True,
        free_tier_confirmed=True,
        max_cost_usd=0,
        input_usd_per_million=0,
        output_usd_per_million=0,
    )
    budget = Budget(tmp_path, limits, "geometry-gate")
    (tmp_path / "cache").mkdir()
    row = runner.assess("hybrid", case, verified, limits, tmp_path, budget, time.monotonic() + 10)
    assert row["status"] == "completed" and row["prediction"] is None
    assert row["reason"] == "unverified_visual_only_cv_geometry_inconclusive"
    assert row["reasoning_scope"] == "unverified_visual_only_cv_geometry_inconclusive"
    assert row["reply"]["observations"] and budget.data["requests"] == 1
    assert len(observed) == 1 and row["generation_started"]
    assert '"cv":' not in json.dumps(observed[0])


def test_rgb_hash_avoids_image_sized_copy():
    import tracemalloc

    from ep_engine.vlm_eval.evidence import pixel_sha

    image = np.zeros((1024, 1024, 3), np.uint8)
    expected = sha(image.tobytes())
    tracemalloc.start()
    assert pixel_sha(image) == expected
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < image.nbytes // 4
    assert pixel_sha(image[::2]) == sha(image[::2].tobytes())


def test_run_releases_collection_before_loading_next(case, tmp_path, monkeypatch):
    import weakref

    import ep_engine.vlm_eval.runner as runner

    original = runner.verified_case
    references = []

    def checked(item):
        assert all(ref() is None for ref in references)
        result = original(item)
        references[:] = [weakref.ref(image.original_rgb) for image in result[2]]
        return result

    monkeypatch.setattr(runner, "verified_case", checked)
    second = case.model_copy(update={"case_id": "second"})
    runner.run(Benchmark(cases=[case, second]), Limits(), tmp_path / "released")
    assert all(ref() is None for ref in references)
