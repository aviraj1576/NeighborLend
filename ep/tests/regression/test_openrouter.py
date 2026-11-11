"""OpenRouter integration controls. All provider calls here use generated data/mocks."""

import json
import time

import httpx
import pytest
from pydantic import ValidationError
from test_vlm_evaluation import Models, positive
from test_vlm_evaluation import case as case

from ep_engine.vlm_eval.api import inspect
from ep_engine.vlm_eval.contracts import Limits, Reply
from ep_engine.vlm_eval.environment import load_environment
from ep_engine.vlm_eval.evidence import prepare, verified_case
from ep_engine.vlm_eval.fusion import CombinedReport, fuse
from ep_engine.vlm_eval.openrouter import OpenRouter, body_for, request_slot, sanitized_error
from ep_engine.vlm_eval.provider import EvaluationError
from ep_engine.vlm_eval.runner import Budget, assess


def limits(**changes):
    return Limits.model_validate(
        dict(
            provider="openrouter",
            model="test/vision:free",
            allow_external=True,
            input_usd_per_million=0,
            output_usd_per_million=0,
            max_cost_usd=0,
            min_request_interval_seconds=0,
            **changes,
        )
    )


def catalog(**changes):
    return {
        "data": [
            dict(
                id="test/vision:free",
                architecture={"input_modalities": ["text", "image"], "output_modalities": ["text"]},
                pricing={"prompt": "0", "completion": "0"},
                context_length=100000,
                supported_parameters=["response_format", "structured_outputs"],
                **changes,
            )
        ]
    }


@pytest.fixture(autouse=True)
def isolated_router_state(tmp_path, monkeypatch):
    monkeypatch.setattr("ep_engine.vlm_eval.openrouter.EP_ROOT", tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


def test_successful_image_roundtrip_strict_json_usage_and_privacy(case):
    config = limits()
    prepared = prepare(case, "vlm_only", config, verified_case(case))
    reply = positive(verified_case(case))
    reply.recapture_guidance = ["Retake from the same viewpoint in diffuse light"]
    seen = []

    def transport(request):
        seen.append(request)
        assert request.url.host == "openrouter.ai"
        if request.method == "GET":
            return httpx.Response(200, json=catalog())
        body = json.loads(request.content)
        assert body["provider"]["max_price"] == {
            "prompt": 0,
            "completion": 0,
            "image": 0,
            "request": 0,
        }
        assert body["provider"]["data_collection"] == "deny"
        assert body["provider"]["allow_fallbacks"] is False
        assert body["response_format"]["json_schema"]["strict"] is True
        assert b"GPS-private-address" not in request.content
        assert b"synthetic-secret-key" not in request.content
        assert body["messages"][1]["content"][2]["image_url"]["url"].startswith(
            "data:image/png;base64,"
        )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": reply.model_dump_json()}}
                ],
                "usage": {"prompt_tokens": 200, "completion_tokens": 50, "cost": 0},
            },
        )

    provider = OpenRouter(config, "synthetic-secret-key", httpx.MockTransport(transport))
    body = body_for(prepared, config, Reply.model_json_schema())
    assert provider.count(body) is None
    result = provider.generate(body)
    assert Reply.model_validate(result["reply"]).change == "visible_difference"
    assert result["usage"]["promptTokenCount"] == 200
    assert result["provider_reported_cost_usd"] == 0
    assert [r.method for r in seen] == ["GET", "POST"]


@pytest.mark.parametrize(
    "mutation,reason",
    [
        (
            {"architecture": {"input_modalities": ["text"], "output_modalities": ["text"]}},
            "model_does_not_support_images",
        ),
        ({"pricing": {"prompt": "0.0001", "completion": "0"}}, "model_not_verified_free"),
        ({"supported_parameters": []}, "model_does_not_support_json_mode"),
        ({"context_length": 100}, "model_context_budget"),
        ({"id": "missing/model:free"}, "model_unavailable"),
    ],
)
def test_metadata_refusal_never_transmits_images(mutation, reason):
    value = catalog()
    value["data"][0].update(mutation)
    seen = []

    def transport(request):
        seen.append(request.method)
        return httpx.Response(200, json=value)

    provider = OpenRouter(limits(), "secret", httpx.MockTransport(transport))
    with pytest.raises(EvaluationError, match=reason):
        provider.count({})
    assert seen == ["GET"]


@pytest.mark.parametrize("status", [302, 401, 429, 503])
def test_http_errors_are_bounded_redacted_and_metadata_retry_only(status):
    calls = []

    def transport(request):
        calls.append(request.method)
        return httpx.Response(status, content=b"secret credential and private provider error")

    provider = OpenRouter(limits(), "secret", httpx.MockTransport(transport))
    with pytest.raises(EvaluationError) as error:
        provider.check_model()
    assert "secret" not in str(error.value)
    assert len(calls) == (2 if status in {429, 503} else 1)


@pytest.mark.parametrize(
    "content,finish,cost,reason",
    [
        ("broken", "stop", 0, "provider_schema"),
        ('{"change":"uncertain","change":"visible_difference"}', "stop", 0, "provider_schema"),
        ('{"value":NaN}', "stop", 0, "provider_schema"),
        ("{}", "length", 0, "provider_refusal_or_truncation"),
        ("{}", "stop", 0.01, "provider_nonzero_cost_reported"),
    ],
)
def test_malformed_truncated_or_nonzero_cost_responses(content, finish, cost, reason):
    def transport(request):
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": finish, "message": {"content": content}}],
                "usage": {"cost": cost},
            },
        )

    provider = OpenRouter(limits(), "secret", httpx.MockTransport(transport))
    provider.metadata = {"structured_outputs": True}
    with pytest.raises(EvaluationError, match=reason):
        provider.generate({})


def test_no_damage_disagreement_identity_and_financial_prohibition(case):
    verified = verified_case(case)
    report = verified[1]
    yes = positive(verified)
    row = dict(
        status="completed",
        reason="cv_vlm_disagreement_requires_human_review",
        prediction=None,
        reply=yes.model_dump(mode="json"),
    )
    combined = fuse(report.inspection_id, "hybrid", report, row)
    assert combined.disagreement and combined.decision == "uncertain"
    assert combined.cv_appearance_prediction is False and combined.vlm_appearance_opinion is True
    assert combined.vlm.interpretation.observations
    assert combined.supported_appearance_prediction is None
    assert not combined.physical_identity_verified and not combined.confirmed_damage
    no = Reply(change="no_visible_difference", uncertainty=["Visible surface only"])
    row.update(reply=no.model_dump(mode="json"), prediction=False)
    assert (
        fuse(report.inspection_id, "hybrid", report, row).supported_appearance_prediction is False
    )
    for field, value in (("physical_identity_verified", True), ("payment_action", "deduct")):
        with pytest.raises(ValidationError):
            Reply.model_validate(dict(no.model_dump(), **{field: value}))
    with pytest.raises(ValidationError):
        CombinedReport.model_validate(dict(combined.model_dump(), confirmed_damage=True))


def test_failed_provider_preserves_cv_and_disable_is_network_free(case, tmp_path, monkeypatch):
    import ep_engine.vlm_eval.api as api

    def forbidden(*args, **kwargs):
        pytest.fail("cv_only and disabled VLM must not create a remote worker")

    monkeypatch.setattr("ep_engine.vlm_eval.runner.LiveCall", forbidden)
    payload = json.loads(case.input_manifest.read_bytes())
    cv = inspect(payload, tmp_path / "cv", models=Models())
    disabled = inspect(payload, tmp_path / "hybrid", mode="hybrid", models=Models())
    assert cv.decision == "cv_only" and cv.vlm is None
    assert disabled.decision == "cv_fallback"
    assert disabled.cv_report.cv_package.outcome == cv.cv_report.cv_package.outcome
    assert disabled.cv_report.cv_package.thresholds == cv.cv_report.cv_package.thresholds
    frozen = disabled.cv_report.model_dump_json()
    fuse(
        disabled.inspection_id,
        "hybrid",
        disabled.cv_report,
        dict(status="failed", reason="provider_timeout", prediction=None),
    )
    assert disabled.cv_report.model_dump_json() == frozen
    # VLM-only execution has no CV/model dependency.
    monkeypatch.setattr(api, "inspect_cv", forbidden)
    vlm = inspect(payload, tmp_path / "vlm", mode="vlm_only")
    assert vlm.cv_report is None and vlm.decision == "uncertain"


def test_explicit_environment_config_never_loads_application_or_echoes_key(tmp_path, monkeypatch):
    source = tmp_path / "settings.env"
    source.write_text(
        "EP_VLM_ENABLED=false\nEP_VLM_PROVIDER=openrouter\n"
        "OPENROUTER_API_KEY=synthetic-secret-key-12345\nDATABASE_URL=never-import\n"
    )
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config, receipt = load_environment(source)
    assert config.provider == "disabled" and not config.allow_external
    assert receipt["credential_present"] and "synthetic-secret" not in json.dumps(receipt)
    import os

    assert "DATABASE_URL" not in os.environ
    with pytest.raises(ValidationError):
        Limits(base_url="https://attacker.example/api/v1")
    with pytest.raises(EvaluationError):
        OpenRouter(limits(), "")


def test_global_concurrency_and_pacing_are_bounded():
    with request_slot(0):
        with pytest.raises(EvaluationError, match="provider_concurrency_limit"):
            with request_slot(0):
                pytest.fail("Concurrent remote operation admitted")


def test_error_diagnostics_whitelist_no_provider_prose_or_keys():
    value = sanitized_error(
        404,
        json.dumps(
            {
                "error": {
                    "code": 404,
                    "message": (
                        "No endpoints matching your data policy. private-secret-and-photo-text"
                    ),
                    "metadata": {"api_key": "must-never-escape"},
                }
            }
        ),
    )
    assert value == dict(
        provider_error_code=404, provider_error_category="privacy_policy_no_eligible_endpoint"
    )
    assert "secret" not in json.dumps(value) and "photo" not in json.dumps(value)
    assert sanitized_error(404, b"not JSON")["provider_error_code"] is None


def test_remote_schema_requires_guidance_and_all_authority_flags(case):
    config = limits(reasoning_enabled=False)
    body = body_for(
        prepare(case, "vlm_only", config, verified_case(case)), config, Reply.model_json_schema()
    )
    remote = body["response_format"]["json_schema"]["schema"]
    assert set(remote["required"]) == set(remote["properties"])
    assert remote["properties"]["recapture_guidance"]["minItems"] == 1
    assert remote["properties"]["uncertainty"]["minItems"] == 1
    assert "CHANGE proposals only" in remote["properties"]["observations"]["description"]
    assert body["reasoning"] == {"enabled": False, "exclude": True}
    assert "recapture_guidance" in remote["required"]
    observation = remote["$defs"]["Observation"]["properties"]
    original_ids = {str(i.id) for i in verified_case(case)[2]}
    assert set(observation["evidence_ids"]["items"]["enum"]) == original_ids
    assert "crop-only citations are invalid" in observation["evidence_ids"]["description"]


def test_unverified_fusion_never_promotes_inconclusive_geometry(case):
    verified = verified_case(case)
    report = verified[1]
    report.cv_package.pairs[0].status = "inconclusive"
    row = dict(
        status="completed",
        reason="unverified_visual_only_cv_geometry_inconclusive",
        reasoning_scope="unverified_visual_only_cv_geometry_inconclusive",
        prediction=None,
        reply=positive(verified).model_dump(mode="json"),
    )
    result = fuse(report.inspection_id, "hybrid", report, row)
    assert result.vlm_appearance_opinion is True and result.vlm.interpretation.observations
    assert result.supported_appearance_prediction is None and result.decision == "uncertain"
    assert result.vlm.findings_verified is False
    assert result.vlm.reasoning_scope == "unverified_visual_only_cv_geometry_inconclusive"
    assert result.physical_identity_verified is False and result.confirmed_damage is False
    row["prediction"] = True  # Fusion independently rejects accidental upstream promotion.
    guarded = fuse(report.inspection_id, "hybrid", report, row)
    assert guarded.supported_appearance_prediction is None
    assert guarded.vlm.supported_prediction is None and guarded.decision == "uncertain"


def test_single_429_retry_reserves_every_attempt(case, tmp_path, monkeypatch):
    import ep_engine.vlm_eval.runner as runner

    count = []
    reply = Reply(
        change="no_visible_difference",
        uncertainty=["Only visible scope"],
        recapture_guidance=["Match angle"],
    )

    class Call:
        def __init__(self, *args):
            count.append(1)
            self.reads = 0

        def receive(self):
            self.reads += 1
            if self.reads == 1:
                return {"count": None}
            if len(count) == 1:
                error = EvaluationError("provider_rejected")
                error.http_status = 429
                raise error
            return {"reply": reply.model_dump(mode="json"), "usage": {}}

        def proceed(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(runner, "LiveCall", Call)
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-secret")
    config = limits(generation_retries=1)
    (tmp_path / "cache").mkdir()
    budget = Budget(tmp_path, config, "retry-control")
    row = assess(
        "vlm_only", case, verified_case(case), config, tmp_path, budget, time.monotonic() + 20
    )
    assert row["status"] == "completed" and budget.data["requests"] == len(count) == 2
