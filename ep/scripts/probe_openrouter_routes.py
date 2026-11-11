"""Bounded free-route diagnostics: public metadata and synthetic text only, no images."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ep_engine.vlm_eval.contracts import Limits
from ep_engine.vlm_eval.environment import load_environment
from ep_engine.vlm_eval.evidence import sha
from ep_engine.vlm_eval.openrouter import OpenRouter
from ep_engine.vlm_eval.provider import EvaluationError
from ep_engine.vlm_eval.runner import Budget, write_json

OUT = Path(__file__).resolve().parents[1] / ".test-artifacts/openrouter-finalization-20261111"


def main():
    OUT.mkdir(parents=True, exist_ok=True, mode=0o700)
    config, receipt = load_environment(Path(__file__).resolve().parents[2] / "backend/.env")
    if config.provider != "openrouter":
        raise ValueError("OpenRouter disabled; no diagnostic calls allowed")
    config = Limits.model_validate(dict(config.model_dump(), allow_external=True, max_requests=4))
    provider = OpenRouter(config, os.environ.get("OPENROUTER_API_KEY", ""))
    public = provider.exchange("GET", "/models")
    account = provider.exchange("GET", "/models/user")
    free = [
        m
        for m in public["data"]
        if m["id"].endswith(":free") and "image" in m["architecture"]["input_modalities"]
    ]
    allowed = {m["id"] for m in account["data"]}
    write_json(
        OUT / "free-vision-metadata.json",
        dict(
            environment=receipt,
            public_free_vision=[
                dict(
                    id=m["id"],
                    pricing=m["pricing"],
                    supported_parameters=m.get("supported_parameters", []),
                    account_catalog_visible=m["id"] in allowed,
                )
                for m in free
            ],
        ),
    )
    candidates = sorted(free, key=lambda m: m["id"] != config.model)
    budget = Budget(OUT, config, "synthetic-free-route-diagnostic-v1")
    records = []
    for item in candidates:
        if not {"response_format", "structured_outputs"} & set(
            item.get("supported_parameters", [])
        ):
            records.append(dict(model=item["id"], status="json_mode_unsupported"))
            continue
        specific = Limits.model_validate(dict(config.model_dump(), model=item["id"]))
        probe = OpenRouter(specific, os.environ.get("OPENROUTER_API_KEY", ""))
        row = dict(model=item["id"], input="synthetic_text_only", images_sent=0)
        try:
            row["capabilities"] = probe.check_model()
            row["endpoints"] = [
                dict(
                    provider=e.get("provider_name"),
                    pricing=e.get("pricing"),
                    status=e.get("status"),
                    supported_parameters=e.get("supported_parameters"),
                )
                for e in probe.exchange("GET", "/models/" + specific.model + "/endpoints")["data"][
                    "endpoints"
                ]
            ]
            budget.reserve(sha(item["id"].encode()))
            response = probe.exchange(
                "POST",
                "/chat/completions",
                dict(
                    model=specific.model,
                    messages=[
                        {
                            "role": "user",
                            "content": "Return the JSON object {}. Synthetic route check.",
                        }
                    ],
                    max_tokens=16,
                    temperature=0,
                    response_format={"type": "json_object"},
                    provider={
                        "allow_fallbacks": False,
                        "require_parameters": True,
                        "data_collection": "deny",
                        "max_price": {"prompt": 0, "completion": 0, "image": 0, "request": 0},
                    },
                ),
            )
            row.update(
                status="synthetic_route_accepted",
                usage=response.get("usage"),
                policy="data_collection_deny_and_zero_price",
            )
        except EvaluationError as exc:
            row.update(
                status=exc.code,
                http_status=getattr(exc, "http_status", None),
                provider_error_code=getattr(exc, "provider_error_code", None),
                provider_error_category=getattr(exc, "provider_error_category", None),
            )
        records.append(row)
        write_json(OUT / "route-diagnostics.json", records)
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
