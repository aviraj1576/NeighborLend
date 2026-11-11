import json

import httpx
import pytest

from ep_engine.assessment.providers import (
    JSONHTTPProvider,
    PreparedRequest,
    ProviderError,
    ProviderSettings,
    configured_provider,
)


def settings(**changes):
    return ProviderSettings(
        endpoint="https://vlm.invalid/assess",
        api_key="test-credential",
        permit_external=True,
        **changes,
    )


@pytest.mark.parametrize(
    "values",
    [
        {"endpoint": "http://vlm.invalid"},
        {"permit_external": False},
        {"api_key": ""},
        {"endpoint": "https://user:password@vlm.invalid"},
    ],
)
def test_configuration_refuses_unsafe_or_unpermitted_transport(values):
    data = settings().model_dump()
    data.update(values)
    with pytest.raises(ProviderError):
        JSONHTTPProvider(ProviderSettings.model_validate(data))


@pytest.mark.parametrize("mode", ["timeout", "server", "bad_json", "oversize", "redirect"])
def test_provider_failure_bounds_and_no_redirects(mode):
    calls = []

    def handle(request):
        calls.append(request)
        if mode == "timeout":
            raise httpx.ReadTimeout("fixture", request=request)
        status = {"server": 503, "redirect": 302}.get(mode, 200)
        return httpx.Response(status, content=b"x" * (1_000_001 if mode == "oversize" else 10))

    provider = JSONHTTPProvider(settings(max_retries=2), httpx.MockTransport(handle))
    with pytest.raises(ProviderError) as caught:
        provider.send(PreparedRequest({"response_schema": {}, "candidates": []}, []))
    assert len(calls) == (3 if mode in ("timeout", "server") else 1)
    assert caught.value.code in {
        "provider_timeout",
        "provider_unavailable",
        "provider_schema",
        "provider_response_limit",
        "provider_rejected",
    }
    assert "test-credential" not in str(caught.value)


def test_structured_transport_usage_and_estimated_cost():
    def handle(request):
        body = json.loads(request.content)
        assert body["model"] == "fixture-model" and body["max_output_tokens"] == 2048
        assert "untrusted" in body["instruction"] and body["images"][0]["base64"] == "YWJj"
        return httpx.Response(
            200,
            json={
                "assessment": {"observations": []},
                "usage": {"input_tokens": 100, "output_tokens": 20},
            },
        )

    provider = JSONHTTPProvider(
        settings(model="fixture-model", input_usd_per_million=1, output_usd_per_million=2),
        httpx.MockTransport(handle),
    )
    result = provider.send(PreparedRequest({}, [{"data": b"abc", "artifact_id": "fixture"}]))
    assert result.attempts == 1 and result.estimated_cost_usd == pytest.approx(0.00014)
    assert configured_provider(ProviderSettings()).kind == "disabled"
