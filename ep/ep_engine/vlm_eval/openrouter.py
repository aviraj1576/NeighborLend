"""Bounded OpenRouter vision transport. No paid routes, remote URLs or raw errors."""

import base64
import json
import math
import os
import re
import time
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation

import httpx

from ep_engine.config import EP_ROOT
from ep_engine.vlm_eval.provider import INSTRUCTION, EvaluationError, response_schema, strict_json


def sanitized_error(status, data):
    """Retain whitelisted codes/categories, never echoed prompts or provider prose."""
    category = "provider_rejection"
    code = None
    try:
        detail = strict_json(data).get("error", {})
        candidate = detail.get("code")
        if type(candidate) is int and 100 <= candidate <= 599:
            code = candidate
        elif isinstance(candidate, str) and candidate in {
            "INVALID_ARGUMENT",
            "NOT_FOUND",
            "RESOURCE_EXHAUSTED",
            "UNAUTHENTICATED",
        }:
            code = candidate
        message = str(detail.get("message", "")).casefold()
        if "data policy" in message or "data collection" in message or "privacy" in message:
            category = "privacy_policy_no_eligible_endpoint"
        elif "no endpoints" in message and ("parameter" in message or "support" in message):
            category = "required_parameters_no_eligible_endpoint"
        elif "no endpoints" in message:
            category = "no_eligible_endpoint"
        elif status in {401, 403}:
            category = "authentication_or_authorization"
        elif status == 429:
            category = "rate_limit"
        elif status == 404 and "model" in message:
            category = "model_not_found"
    except (ValueError, TypeError, AttributeError):
        pass
    return dict(provider_error_code=code, provider_error_category=category)


@contextmanager
def request_slot(interval):
    """One host-wide OpenRouter operation; shared across workers and campaigns.

    OS advisory locks release on process death. The persistent timestamp enforces
    pacing across processes; contention fails closed rather than spawning a queue.
    """
    from ep_engine.vlm_eval.evidence import safe_path

    root = safe_path(EP_ROOT / ".runtime/vlm-openrouter")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = safe_path(root / "provider.lock")
    stamp = safe_path(root / "next-request.txt")
    with lock.open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise EvaluationError("provider_concurrency_limit") from None
        try:
            previous = float(stamp.read_text()) if stamp.exists() else 0
            if not math.isfinite(previous):
                raise EvaluationError("provider_rate_state_invalid")
            delay = previous - time.time()
            if delay > interval + 1:
                raise EvaluationError("provider_rate_limit")
            if delay > 0:
                time.sleep(delay)
            with stamp.open("w") as record:
                record.write(str(time.time() + interval))
                record.flush()
                os.fsync(record.fileno())
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def required_reply_schema(schema):
    compact = response_schema(schema)

    def require_fields(value):
        if isinstance(value, dict):
            if value.get("type") == "object" and "properties" in value:
                value["required"] = list(value["properties"])
            for child in value.values():
                require_fields(child)
        elif isinstance(value, list):
            for child in value:
                require_fields(child)

    require_fields(compact)
    compact["properties"]["recapture_guidance"]["minItems"] = 1
    compact["properties"]["uncertainty"]["minItems"] = 1
    compact["properties"]["observations"]["description"] = (
        "CHANGE proposals only. Return [] for no_visible_difference and uncertain; "
        "only visible_difference may have observations."
    )
    return compact


def body_for(prepared, limits, schema, structured=True):
    remote_schema = required_reply_schema(schema)
    pairs = prepared["evidence"].get("source_pairs", [])
    if pairs:
        observation = remote_schema["$defs"]["Observation"]["properties"]
        observation["before_id"]["enum"] = sorted({p["before_id"] for p in pairs})
        observation["after_id"]["enum"] = sorted({p["after_id"] for p in pairs})
        observation["evidence_ids"]["items"]["enum"] = [i["id"] for i in prepared["images"]]
        observation["evidence_ids"]["description"] = (
            "MUST include BOTH the before_id AND after_id original image UUIDs. "
            "Attached crop UUIDs may be added; crop-only citations are invalid."
        )
    content = [{"type": "text", "text": json.dumps(prepared["evidence"], allow_nan=False)}]
    for image in prepared["images"]:
        content.extend(
            [
                {
                    "type": "text",
                    "text": json.dumps({k: v for k, v in image.items() if k != "data"}),
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,"
                        + base64.b64encode(image["data"]).decode("ascii"),
                    },
                },
            ]
        )
    # Strict local schema is authoritative, even when a model supports only JSON mode.
    instruction = INSTRUCTION + (
        "\nInclude recapture_guidance (1 to 6 practical suggestions) and distinguish "
        "appearance_only from possible_damage_indicator; neither confirms damage.\n"
        "observations means CHANGE proposals, never general scene descriptions. "
        "For no_visible_difference OR uncertain, observations MUST be []. "
        "For visible_difference, observations MUST contain at least one grounded proposal. "
        "Return every required field, including recapture_guidance and all safety flags.\n"
        "Every observation.evidence_ids MUST include BOTH original before_id and after_id. "
        "Crops are optional extra citations and never replace those original IDs.\n"
        "Required JSON schema: " + json.dumps(remote_schema, allow_nan=False)
    )
    formatting = (
        {
            "type": "json_schema",
            "json_schema": {
                "name": "ep_visual_observations",
                "strict": True,
                "schema": remote_schema,
            },
        }
        if structured
        else {"type": "json_object"}
    )
    body = dict(
        model=limits.model,
        messages=[{"role": "system", "content": instruction}, {"role": "user", "content": content}],
        response_format=formatting,
        max_tokens=limits.max_output_tokens,
        temperature=0,
        stream=False,
        provider={
            "allow_fallbacks": False,
            "require_parameters": True,
            "data_collection": "deny",
            "max_price": {
                "prompt": 0,
                "completion": 0,
                "image": 0,
                "request": 0,
            },
        },
    )
    if limits.reasoning_enabled is not None:
        body["reasoning"] = {"enabled": limits.reasoning_enabled, "exclude": True}
    return body


class OpenRouter:
    def __init__(self, limits, key, transport=None):
        if (
            limits.provider != "openrouter"
            or not limits.allow_external
            or not key
            or not re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+:free", limits.model)
            or not limits.free_only
            or limits.max_cost_usd != 0
            or limits.input_usd_per_million != 0
            or limits.output_usd_per_million != 0
            or limits.base_url != "https://openrouter.ai/api/v1"
        ):
            raise EvaluationError("openrouter_free_configuration_required")
        self.limits, self.key, self.transport = limits, key, transport
        self.metadata = None

    def exchange(self, method, path, body=None):
        try:
            with (
                request_slot(self.limits.min_request_interval_seconds),
                httpx.Client(
                    timeout=self.limits.request_seconds,
                    follow_redirects=False,
                    trust_env=False,
                    transport=self.transport,
                ) as client,
            ):
                with client.stream(
                    method,
                    self.limits.base_url + path,
                    json=body,
                    headers={"Authorization": "Bearer " + self.key, "Accept-Encoding": "identity"},
                ) as response:
                    if response.status_code != 200:
                        error = EvaluationError("provider_rejected")
                        error.http_status = response.status_code
                        diagnostic = bytearray()
                        if response.headers.get("content-encoding", "identity") == "identity":
                            for chunk in response.iter_bytes(chunk_size=4096):
                                if len(diagnostic) + len(chunk) > 65536:
                                    break
                                diagnostic.extend(chunk)
                        for name, value in sanitized_error(
                            response.status_code, diagnostic
                        ).items():
                            setattr(error, name, value)
                        raise error
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise EvaluationError("response_encoding_rejected")
                    maximum = 4_000_000 if method == "GET" else 262144
                    data = bytearray()
                    for chunk in response.iter_bytes(chunk_size=65536):
                        if len(data) + len(chunk) > maximum:
                            raise EvaluationError("response_too_large")
                        data.extend(chunk)
            return strict_json(data)
        except (httpx.HTTPError, ValueError):
            raise EvaluationError("provider_transport_or_json") from None

    def check_model(self):
        for attempt in range(self.limits.metadata_retries + 1):
            try:
                catalog = self.exchange("GET", "/models")
                break
            except EvaluationError as exc:
                if attempt == self.limits.metadata_retries or getattr(
                    exc, "http_status", None
                ) not in {429, 500, 502, 503, 504}:
                    raise
        try:
            rows = [m for m in catalog["data"] if m["id"] == self.limits.model]
            if len(rows) != 1:
                raise EvaluationError("model_unavailable")
            model = rows[0]
            if "image" not in model["architecture"]["input_modalities"]:
                raise EvaluationError("model_does_not_support_images")
            if "text" not in model["architecture"]["output_modalities"]:
                raise EvaluationError("model_does_not_support_text")
            parameters = model.get("supported_parameters", [])
            if "response_format" not in parameters and "structured_outputs" not in parameters:
                raise EvaluationError("model_does_not_support_json_mode")
            prices = model["pricing"]
            if not {"prompt", "completion"} <= prices.keys() or any(
                not Decimal(str(price)).is_finite() or Decimal(str(price)) != 0
                for price in prices.values()
            ):
                raise EvaluationError("model_not_verified_free")
            if (
                model["context_length"]
                < self.limits.max_input_tokens + self.limits.max_output_tokens
            ):
                raise EvaluationError("model_context_budget")
            self.metadata = dict(
                model=model["id"],
                input_modalities=model["architecture"]["input_modalities"],
                pricing=prices,
                structured_outputs="structured_outputs" in parameters,
                supports_reasoning="reasoning" in parameters,
            )
            return self.metadata
        except (KeyError, TypeError, InvalidOperation):
            raise EvaluationError("model_metadata_invalid") from None

    def count(self, body):
        self.check_model()
        # OpenRouter provides no model-independent exact token count endpoint.
        # Do not fabricate a count. Free routing and max_tokens bound financial risk.
        return None

    def generate(self, body):
        if self.metadata is None:
            raise EvaluationError("model_capability_check_required")
        if "reasoning" in body and not self.metadata.get("supports_reasoning"):
            raise EvaluationError("model_reasoning_control_unsupported")
        if not self.metadata["structured_outputs"]:
            body = dict(body, response_format={"type": "json_object"})
        result = self.exchange("POST", "/chat/completions", body)
        try:
            choices = result["choices"]
            if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
                raise EvaluationError("provider_refusal_or_truncation")
            message = choices[0]["message"]
            if message.get("tool_calls") or message.get("refusal"):
                raise EvaluationError("provider_tool_or_refusal")
            usage = result.get("usage", {})
            cost = usage.get("cost")
            if cost is not None and (not math.isfinite(float(cost)) or float(cost) != 0):
                raise EvaluationError("provider_nonzero_cost_reported")
            return dict(
                reply=strict_json(message["content"]),
                usage=dict(
                    promptTokenCount=usage.get("prompt_tokens"),
                    candidatesTokenCount=usage.get("completion_tokens"),
                    thoughtsTokenCount=0,
                ),
                provider_reported_cost_usd=cost,
                model_metadata=self.metadata,
            )
        except (KeyError, TypeError, ValueError):
            raise EvaluationError("provider_schema") from None
