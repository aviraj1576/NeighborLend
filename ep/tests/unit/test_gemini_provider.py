"""Gemini wire compatibility without network access or photographic fixtures."""

import json

import httpx
import pytest

from ep_engine.assessment.contracts import ProviderReply
from ep_engine.assessment.providers import (
    PreparedRequest,
    ProviderError,
    ProviderSettings,
    configured_provider,
)


def settings(**changes):
    values = dict(
        provider="gemini",
        model="gemini-test-model",
        api_key="synthetic-secret",
        permit_external=True,
    )
    return ProviderSettings(**(values | changes))


def prepared():
    return PreparedRequest(
        {"response_schema": ProviderReply.model_json_schema(), "candidates": []},
        [{"data": b"synthetic-pixels", "artifact_id": "synthetic-id", "media_type": "image/png"}],
    )


def reply(**changes):
    return {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {"role": "model", "parts": [{"text": '{"observations": []}'}]},
            }
        ],
        **changes,
    }


def provider_with_transport(transport, **changes):
    from ep_engine.assessment.providers import GeminiProvider

    return GeminiProvider(settings(**changes), transport)


def test_environment_credentials_are_explicit_provider_specific_and_secret(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-google-key")
    assert configured_provider().kind == "disabled"
    monkeypatch.setenv("EP_VLM_PROVIDER", "gemini")
    monkeypatch.setenv("EP_VLM_API_KEY", "synthetic-gateway-key")
    monkeypatch.setenv("EP_VLM_MODEL", "gemini-test-model")
    with pytest.raises(ProviderError, match="provider_configuration"):
        configured_provider()
    monkeypatch.setenv("EP_VLM_ALLOW_EXTERNAL", "1")
    provider = configured_provider()
    assert provider.kind == "gemini" and not provider.mocked
    assert provider.settings.api_key.get_secret_value() == "synthetic-google-key"
    assert "synthetic-google-key" not in repr(provider.settings)
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(ProviderError, match="provider_configuration"):
        configured_provider()
    monkeypatch.setenv("EP_VLM_PROVIDER", "json_http")
    assert ProviderSettings.from_environment().api_key.get_secret_value() == "synthetic-gateway-key"
    monkeypatch.setenv("EP_VLM_PROVIDER", "mock")
    assert configured_provider().mocked


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "unconfigured"},
        {"model": "models/gemini-test"},
        {"model": "gemini-test?key=secret"},
        {"model": "gemini-../escape"},
        {"endpoint": "https://attacker.invalid/"},
        {"endpoint": "https://generativelanguage.googleapis.com/redirect"},
        {"api_key": ""},
        {"permit_external": False},
    ],
)
def test_gemini_rejects_missing_consent_credentials_and_endpoint_injection(changes):
    with pytest.raises(ProviderError, match="provider_configuration"):
        provider_with_transport(
            httpx.MockTransport(lambda r: pytest.fail("Network attempt")), **changes
        )


def test_official_request_images_schema_headers_and_usage():
    def handle(request):
        assert str(request.url) == (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-test-model:generateContent"
        )
        assert request.method == "POST" and not request.url.query
        assert request.headers["x-goog-api-key"] == "synthetic-secret"
        assert "authorization" not in request.headers
        assert request.headers["accept-encoding"] == "identity"
        body = json.loads(request.content)
        assert "untrusted" in body["systemInstruction"]["parts"][0]["text"]
        assert "confirmed physical damage" in body["systemInstruction"]["parts"][0]["text"]
        assert body["generationConfig"] == {
            "maxOutputTokens": 2048,
            "candidateCount": 1,
            "responseMimeType": "application/json",
            "responseJsonSchema": ProviderReply.model_json_schema(),
        }
        assert "tools" not in body and "safetySettings" not in body
        contents = body["contents"]
        assert len(contents) == 1 and contents[0]["role"] == "user"
        parts = contents[0]["parts"]
        assert json.loads(parts[0]["text"])["candidates"] == []
        assert json.loads(parts[1]["text"])["artifact_id"] == "synthetic-id"
        assert parts[2] == {
            "inlineData": {"mimeType": "image/png", "data": "c3ludGhldGljLXBpeGVscw=="}
        }
        assert "synthetic-secret" not in request.content.decode()
        return httpx.Response(
            200,
            json=reply(
                usageMetadata={
                    "promptTokenCount": 100,
                    "candidatesTokenCount": 20,
                    "thoughtsTokenCount": 5,
                    "totalTokenCount": 125,
                }
            ),
        )

    result = provider_with_transport(
        httpx.MockTransport(handle),
        input_usd_per_million=1,
        output_usd_per_million=2,
    ).send(prepared())
    assert json.loads(result.content) == {"observations": []}
    assert result.usage.input_tokens == 100 and result.usage.output_tokens == 25
    assert result.estimated_cost_usd == pytest.approx(0.00015) and result.attempts == 1


def test_split_text_ignores_thoughts_and_absent_usage_stays_unknown():
    data = reply()
    data["candidates"][0]["content"]["parts"] = [
        {"thought": True, "text": "Private reasoning, not assessment"},
        {"text": '{"observations":'},
        {"text": " []}"},
    ]
    result = provider_with_transport(
        httpx.MockTransport(lambda r: httpx.Response(200, json=data))
    ).send(prepared())
    assert json.loads(result.content) == {"observations": []}
    assert result.usage.input_tokens is None and result.usage.output_tokens is None
    assert result.estimated_cost_usd is None


@pytest.mark.parametrize(
    "data,code",
    [
        ({"promptFeedback": {"blockReason": "SAFETY"}}, "provider_rejected"),
        (reply(candidates=[]), "provider_schema"),
        (reply(candidates=[{}, {}]), "provider_schema"),
        ([], "provider_schema"),
        (reply(candidates=None), "provider_schema"),
        (reply(usageMetadata={"promptTokenCount": -1}), "provider_schema"),
        (reply(usageMetadata={"candidatesTokenCount": "20"}), "provider_schema"),
        (reply(usageMetadata={"thoughtsTokenCount": True}), "provider_schema"),
    ],
)
def test_invalid_or_blocked_responses_fail_closed(data, code):
    provider = provider_with_transport(
        httpx.MockTransport(lambda r: httpx.Response(200, json=data))
    )
    with pytest.raises(ProviderError) as caught:
        provider.send(prepared())
    assert caught.value.code == code and caught.value.attempts == 1
    assert "synthetic-secret" not in str(caught.value)


@pytest.mark.parametrize("finish", ["MAX_TOKENS", "SAFETY", "RECITATION", "OTHER", None])
def test_partial_and_refused_generation_never_becomes_an_assessment(finish):
    data = reply()
    data["candidates"][0]["finishReason"] = finish
    provider = provider_with_transport(
        httpx.MockTransport(lambda r: httpx.Response(200, json=data))
    )
    with pytest.raises(ProviderError, match="provider_rejected"):
        provider.send(prepared())


@pytest.mark.parametrize(
    "parts", [[], [{"text": ""}], [{"inlineData": {}}], [{"thought": True, "text": "thought"}]]
)
def test_no_final_text_is_rejected(parts):
    data = reply()
    data["candidates"][0]["content"]["parts"] = parts
    with pytest.raises(ProviderError, match="provider_schema"):
        provider_with_transport(httpx.MockTransport(lambda r: httpx.Response(200, json=data))).send(
            prepared()
        )


@pytest.mark.parametrize(
    "failure,code,attempts",
    [
        (429, "provider_unavailable", 3),
        (503, "provider_unavailable", 3),
        (400, "provider_rejected", 1),
        (401, "provider_rejected", 1),
        (302, "provider_rejected", 1),
        ("timeout", "provider_timeout", 3),
        ("network", "provider_unavailable", 3),
        ("oversize", "provider_response_limit", 1),
        ("compressed", "provider_response_limit", 1),
        ("json", "provider_schema", 1),
    ],
)
def test_transport_failures_are_bounded_sanitized_and_never_redirect(failure, code, attempts):
    calls = []

    def handle(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic-secret", request=request)
        if failure == "network":
            raise httpx.ConnectError("synthetic-secret", request=request)
        if failure == "oversize":
            return httpx.Response(200, content=b"x" * 1_000_001)
        if failure == "compressed":
            return httpx.Response(200, headers={"content-encoding": "br"})
        if failure == "json":
            return httpx.Response(200, content=b"not-json")
        return httpx.Response(failure, headers={"Location": "https://attacker.invalid/"})

    with pytest.raises(ProviderError) as caught:
        provider_with_transport(httpx.MockTransport(handle), max_retries=2).send(prepared())
    assert len(calls) == attempts and caught.value.attempts == attempts
    assert caught.value.code == code and "synthetic-secret" not in str(caught.value)
