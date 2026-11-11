"""Authorized campaign: one synthetic schema check, then at most two phone image calls."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ep_engine.vlm_eval.contracts import Benchmark, Limits, Reply
from ep_engine.vlm_eval.environment import load_environment
from ep_engine.vlm_eval.evidence import sha, validate_citations, verified_case
from ep_engine.vlm_eval.fusion import CombinedReport, fuse
from ep_engine.vlm_eval.provider import LiveCall, request_body
from ep_engine.vlm_eval.runner import Budget, assess, canonical, exclusive, summarize, write_json

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".test-artifacts/openrouter-finalization-20261111"


def main():
    directory = BASE / "validated-live"
    if (directory / "summary.json").exists():
        print("Completed campaign retained; no API calls or output overwrites.")
        return
    directory.mkdir(mode=0o700, exist_ok=True)  # Existing context/ledger must match on resume.
    (directory / "cache").mkdir(mode=0o700, exist_ok=True)
    configured, receipt = load_environment(ROOT.parent / "backend/.env")
    config = Limits.model_validate(
        dict(
            configured.model_dump(),
            model="dots-studio/dots-3-note-preview:free",
            allow_external=True,
            max_requests=3,
            max_images=5,
            reasoning_enabled=False,
            max_output_tokens=4096,
            run_seconds=240,
        )
    )
    manifest = Benchmark.model_validate_json((BASE / "live-manifest.json").read_bytes())
    case = next(c for c in manifest.cases if c.case_id == "phone-front")
    selected = Benchmark(cases=[case])
    prepared = dict(
        evidence={
            "task": "No images provided. Return uncertain with observations=[]; request captures.",
            "source_pairs": [],
        },
        images=[],
        original_ids=[],
    )
    body = request_body(prepared, config, Reply.model_json_schema())
    started = time.monotonic()
    with exclusive(directory):
        budget = Budget(
            directory,
            config,
            sha(
                canonical(
                    dict(
                        manifest=selected.model_dump(mode="json"),
                        config=config.model_dump(),
                        authorization="one-synthetic-two-phone-images",
                    )
                )
            ),
        )
        if (directory / "synthetic-result.json").exists():
            result = json.loads((directory / "synthetic-result.json").read_bytes())
        else:
            budget.reserve(sha(canonical(body)))
            call = LiveCall(config, body)
            try:
                call.receive()
                call.proceed()
                result = call.receive()
            finally:
                call.close()
            write_json(directory / "synthetic-result.json", result)
        reply = Reply.model_validate(result["reply"])
        validate_citations(reply, prepared)
        if reply.change != "uncertain" or not reply.recapture_guidance:
            raise ValueError("Synthetic full-schema check failed; do not send images")
        verified = verified_case(case)
        rows = [
            assess(
                "cv_only", case, verified, config, directory, budget, started + config.run_seconds
            )
        ]
        for mode in ("vlm_only", "hybrid"):
            row = assess(
                mode, case, verified, config, directory, budget, started + config.run_seconds
            )
            rows.append(row)
            write_json(directory / "results.json", rows)
            combined = fuse(
                verified[1].inspection_id, mode, verified[1] if mode == "hybrid" else None, row
            )
            write_json(directory / f"phone-front-{mode}.json", combined.model_dump(mode="json"))
        write_json(directory / "cold-results.json", rows)
        warm = []
        # A failed arm has no cache; do not retry it or reserve another request.
        for row in rows[1:]:
            if row["status"] == "completed":
                cached = assess(
                    row["mode"], case, verified, config, directory, budget, time.monotonic() + 30
                )
                if not cached["cache_hit"]:
                    raise ValueError("Expected validated cache reuse")
                warm.append(cached)
        write_json(directory / "warm-results.json", warm)
        summary = summarize(selected, rows)
        summary.update(
            budget=budget.data,
            total_wall_seconds=time.monotonic() - started,
            images_generation_cap=2,
            synthetic_generation_cap=1,
        )
        write_json(directory / "summary.json", summary)
        write_json(directory / "config.json", config.model_dump(mode="json"))
        write_json(directory / "manifest.json", selected.model_dump(mode="json"))
        write_json(
            directory / "model-selection.json",
            dict(
                environment=receipt,
                selected_model=config.model,
                explicit_override=True,
                privacy="data_collection_deny",
                paid_fallback=False,
            ),
        )
        for name, contract in (("reply", Reply), ("combined-report", CombinedReport)):
            write_json(directory / f"{name}.schema.json", contract.model_json_schema())
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
