"""Matched, label-blind experiments with durable reservations and private JSON caching."""

import json
import os
import statistics
import time
from collections import Counter
from contextlib import contextmanager
from decimal import Decimal

from pydantic import ValidationError

from ep_engine.cv.evaluation import binary_metrics
from ep_engine.cv.numerics import finite_tree
from ep_engine.vlm_eval.contracts import Benchmark, Reply
from ep_engine.vlm_eval.evidence import (
    constrained_prediction,
    cv_prediction,
    pixel_sha,
    prepare,
    safe_path,
    sha,
    verified_case,
    verified_pairs,
)
from ep_engine.vlm_eval.provider import (
    INSTRUCTION,
    PROMPT_VERSION,
    EvaluationError,
    LiveCall,
    request_body,
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def write_json(path, value):
    path = safe_path(path)
    # Diagnostic snapshots have one lock-protected writer. In-place publication
    # avoids Windows DELETE-sharing failures on replace. A partial snapshot is
    # invalid and rejected, never used as a cost/authority record.
    with path.open("wb") as stream:
        if os.name != "nt":
            os.chmod(path, 0o600)
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def exclusive(directory):
    lock = directory / "run.lock"
    stream = lock.open("x")
    try:
        yield
    finally:
        stream.close()
        lock.unlink()


class Budget:
    def __init__(self, directory, limits, context):
        self.path = safe_path(directory / "budget.json")
        self.ledger = safe_path(directory / "budget.jsonl")
        self.limits = limits
        self.data = (
            json.loads(self.path.read_bytes())
            if self.path.exists()
            else dict(context=context, requests=0, reserved_usd="0", attempts=[])
        )
        if self.data["context"] != context:
            raise ValueError("Cannot reuse a run directory for a different manifest/configuration")
        if self.ledger.exists():
            events = [json.loads(line) for line in self.ledger.read_bytes().splitlines()]
            if any(e["context"] != context or e["index"] != i + 1 for i, e in enumerate(events)):
                raise ValueError("Invalid reservation ledger")
            self.data["requests"] = len(events)
            self.data["reserved_usd"] = str(
                sum((Decimal(e["reserved_usd"]) for e in events), Decimal(0))
            )
            self.data["attempts"] = events
        elif self.data["requests"]:
            raise ValueError("Reservation ledger is missing; refusing to reset spent budget")
        write_json(self.path, self.data)

    def reserve(self, fingerprint):
        limits = self.limits
        if limits.input_usd_per_million is None or limits.output_usd_per_million is None:
            raise EvaluationError("explicit_token_prices_required")
        if self.data["requests"] >= limits.max_requests:
            raise EvaluationError("request_budget_exhausted")
        maximum = (
            Decimal(limits.max_input_tokens) * Decimal(str(limits.input_usd_per_million))
            + Decimal(limits.max_output_tokens) * Decimal(str(limits.output_usd_per_million))
        ) / Decimal(1_000_000)
        total = Decimal(self.data["reserved_usd"]) + maximum
        if total > Decimal(str(limits.max_cost_usd)):
            raise EvaluationError("cost_budget_exhausted")
        self.data["requests"] += 1
        self.data["reserved_usd"] = str(total)
        event = dict(
            context=self.data["context"],
            index=self.data["requests"],
            fingerprint=fingerprint,
            reserved_usd=str(maximum),
        )
        self.data["attempts"].append(event)
        # Reserve before a potentially billable call. Failures/timeouts never refund.
        with self.ledger.open("ab") as stream:
            stream.write(canonical(event) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        write_json(self.path, self.data)


def cache_key(prepared, mode, limits, case):
    return sha(
        canonical(
            dict(
                prompt=INSTRUCTION,
                prompt_version=PROMPT_VERSION,
                schema=Reply.model_json_schema(),
                transport_revision="openrouter-vision-4-explicit-source-citations",
                reasoning_enabled=limits.reasoning_enabled,
                provider=limits.provider,
                model=limits.model,
                output_tokens=limits.max_output_tokens,
                mode=mode,
                evidence=prepared["evidence"],
                images=[dict(id=i["id"], sha256=sha(i["data"])) for i in prepared["images"]],
                cv_sha256=case.cv_sha256 if mode == "hybrid" else None,
                account=sha(
                    os.environ.get(
                        "OPENROUTER_API_KEY"
                        if limits.provider == "openrouter"
                        else "GEMINI_API_KEY",
                        "",
                    ).encode()
                )
                if limits.provider in {"gemini", "openrouter"}
                else None,
            )
        )
    )


def assess(mode, case, verified, limits, directory, budget, deadline):
    started = time.monotonic()
    row = dict(
        case_id=case.case_id,
        mode=mode,
        status="not_run",
        prediction=None,
        findings_unverified=True,
        physical_identity_verified=False,
        payment_action="none",
        human_review_required=True,
        cache_hit=False,
        live_inference=False,
        generation_started=False,
    )
    if mode == "cv_only":
        row.update(
            status="completed",
            prediction=cv_prediction(verified[1]),
            reason="replayed_verified_cv_evidence",
            elapsed_seconds=time.monotonic() - started,
        )
        return row
    unverified_route = mode == "hybrid" and not verified_pairs(verified[1].cv_package)
    row["reasoning_scope"] = (
        "unverified_visual_only_cv_geometry_inconclusive"
        if unverified_route
        else "cv_supported_regions"
        if mode == "hybrid"
        else "unverified_visual_only"
    )
    if time.monotonic() >= deadline:
        row.update(reason="run_deadline", elapsed_seconds=time.monotonic() - started)
        return row
    if limits.provider == "disabled":
        row.update(reason="provider_unconfigured", elapsed_seconds=time.monotonic() - started)
        return row
    if limits.provider in {"gemini", "openrouter"} and (
        not limits.allow_external
        or not os.environ.get(
            "OPENROUTER_API_KEY" if limits.provider == "openrouter" else "GEMINI_API_KEY"
        )
    ):
        row.update(
            reason="external_consent_or_credential_missing",
            elapsed_seconds=time.monotonic() - started,
        )
        return row
    if (
        limits.provider == "gemini"
        and limits.free_only
        and not (
            limits.free_tier_confirmed
            and limits.max_cost_usd == 0
            and limits.input_usd_per_million == 0
            and limits.output_usd_per_million == 0
        )
    ):
        row.update(
            reason="free_tier_billing_confirmation_required",
            elapsed_seconds=time.monotonic() - started,
        )
        return row
    try:
        prepared = prepare(case, "vlm_only" if unverified_route else mode, limits, verified)
        if unverified_route:
            prepared["evidence"]["cv_scope"] = {
                "geometry": "inconclusive",
                "geometrically_verified_change_allowed": False,
                "instruction": "Independent visual observations only; retain uncertainty.",
            }
    except ValueError:
        row.update(
            status="not_run",
            reason="request_evidence_budget",
            elapsed_seconds=time.monotonic() - started,
        )
        return row
    key = cache_key(prepared, mode, limits, case)
    cache = safe_path(directory / "cache" / f"{key}.json")
    row["request_fingerprint"] = key
    row["input_pixel_hashes"] = prepared["input_pixels_sha256"]
    row["images_sent"] = len(prepared["images"])
    call = None
    result = None
    try:
        if cache.exists():
            if cache.stat().st_size > 300_000:
                raise EvaluationError("cache_integrity")
            envelope = json.loads(cache.read_bytes())
            if (
                envelope.get("fingerprint") != key
                or sha(canonical(envelope["result"])) != envelope["result_sha256"]
            ):
                raise EvaluationError("cache_integrity")
            result = envelope["result"]
            row["cache_hit"] = True
        elif limits.provider == "offline_fixture":
            result = dict(
                reply=Reply(
                    change="uncertain", uncertainty=["Offline transport fixture; no VLM inference"]
                ).model_dump(mode="json"),
                usage={},
            )
        else:
            # Price and request admission happen before countTokens exports any image.
            budget.reserve(key)
            remaining = min(limits.request_seconds, deadline - time.monotonic())
            if remaining <= 0:
                raise EvaluationError("run_deadline")
            for attempt in range(limits.generation_retries + 1):
                if attempt:
                    budget.reserve(key)
                    remaining = min(limits.request_seconds, deadline - time.monotonic())
                    if remaining <= 0:
                        raise EvaluationError("run_deadline")
                call = LiveCall(
                    limits.model_copy(update={"request_seconds": remaining}),
                    request_body(prepared, limits, Reply.model_json_schema()),
                )
                try:
                    preflight = call.receive()
                    count = preflight["count"]
                    row["preflight_input_tokens"] = count
                    row["token_preflight"] = (
                        "provider_count" if count is not None else "unavailable"
                    )
                    row["model_metadata"] = preflight.get("model_metadata")
                    row["generation_started"] = True
                    call.proceed()
                    result = call.receive()
                    break
                except EvaluationError as exc:
                    # Only explicit 429 rejection is retryable; ambiguous network/
                    # timeout/server failures can have consumed a generation already.
                    if (
                        attempt == limits.generation_retries
                        or getattr(exc, "http_status", None) != 429
                    ):
                        raise
                finally:
                    call.close()
                    call = None
            result["preflight_input_tokens"] = count
        reply = Reply.model_validate(result["reply"])
        if limits.provider == "openrouter" and not reply.recapture_guidance:
            row["validation_rule"] = "recapture_guidance_required"
            raise ValueError("OpenRouter observations require recapture guidance")
        prepared["_artifacts"] = verified[3]
        prediction, reason = constrained_prediction(reply, mode, verified[1], prepared)
        usage = result.get("usage", {})
        values = [
            usage.get(k) for k in ("promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount")
        ]
        if any(v is not None and (type(v) is not int or v < 0) for v in values):
            raise EvaluationError("provider_usage_invalid")
        cost = None
        if values[0] is not None and values[1] is not None:
            output = values[1] + (values[2] or 0)
            if values[0] > limits.max_input_tokens or output > limits.max_output_tokens:
                raise EvaluationError("provider_usage_exceeded_reservation")
            cost = (
                values[0] * limits.input_usd_per_million + output * limits.output_usd_per_million
            ) / 1_000_000
        row.update(
            status="completed"
            if limits.provider in {"gemini", "openrouter"}
            else "offline_fixture",
            prediction=prediction,
            reason=reason,
            reply=reply.model_dump(mode="json"),
            live_inference=limits.provider in {"gemini", "openrouter"},
            usage=usage,
            estimated_cost_usd=cost,
            provider_reported_cost_usd=result.get("provider_reported_cost_usd"),
        )
        if not cache.exists():
            write_json(
                cache, dict(fingerprint=key, result=result, result_sha256=sha(canonical(result)))
            )
    except EvaluationError as exc:
        row.update(
            status="not_run" if exc.code.endswith(("required", "exhausted")) else "failed",
            reason=exc.code,
            http_status=getattr(exc, "http_status", None),
            provider_error_code=getattr(exc, "provider_error_code", None),
            provider_error_category=getattr(exc, "provider_error_category", None),
        )
    except (ValueError, KeyError, TypeError) as exc:
        row.update(status="failed", reason="reply_or_evidence_validation")
        if isinstance(exc, ValidationError):
            row["validation_errors"] = [
                dict(location=list(e["loc"]), type=e["type"])
                for e in exc.errors(include_input=False, include_url=False)
            ]
        else:
            row["validation_exception_type"] = type(exc).__name__
        # Quarantine structured model output privately for offline diagnosis.
        # It is never admitted to the successful-result cache or scored as truth.
        if isinstance(result, dict) and "reply" in result:
            rejected = safe_path(directory / "rejected")
            rejected.mkdir(exist_ok=True, mode=0o700)
            write_json(rejected / f"{key}.json", dict(fingerprint=key, result=result))
    finally:
        if call is not None:
            call.close()
    row["elapsed_seconds"] = time.monotonic() - started
    return row


def summarize(benchmark, rows):
    modes = {}
    completed = {
        mode: {r["case_id"] for r in rows if r["mode"] == mode and r["status"] == "completed"}
        for mode in ("cv_only", "vlm_only", "hybrid")
    }
    common = set.intersection(*completed.values())
    for mode in ("cv_only", "vlm_only", "hybrid"):
        records = [r for r in rows if r["mode"] == mode]
        by_id = {r["case_id"]: r for r in records}
        modes[mode] = dict(
            statuses=dict(Counter(r["status"] for r in records)),
            positive_unverified=sum(r.get("prediction") is True for r in records),
            abstentions=sum(r.get("prediction") is None for r in records),
            live_requests=sum(
                r.get("generation_started", False) and not r["cache_hit"] for r in records
            ),
            accepted_live_responses=sum(r.get("live_inference", False) for r in records),
            cache_hits=sum(r["cache_hit"] for r in records),
            median_record_seconds=statistics.median(r.get("elapsed_seconds", 0) for r in records)
            if records
            else None,
            metrics={},
        )
        for split in ("development", "calibration", "test", "software_control"):
            cases = [c for c in benchmark.cases if c.split == split]
            labels = [c.label.change_present if c.label else None for c in cases]
            # Fixture outputs and failed/not-run arms are always missing predictions.
            predicted = [
                by_id[c.case_id].get("prediction")
                if by_id[c.case_id]["status"] == "completed"
                else None
                for c in cases
            ]
            metrics = binary_metrics(labels, predicted)
            positives = sum(v is True for v in labels)
            metrics["positive_labels_including_abstentions"] = positives
            metrics["recall_lower_bound_including_abstentions"] = (
                metrics.get("tp", 0) / positives if positives else None
            )
            modes[mode]["metrics"][split] = metrics
    return dict(
        modes=modes,
        independently_labeled_cases=sum(c.label is not None for c in benchmark.cases),
        physical_damage_accuracy=None,
        paired_completed_case_ids=sorted(common),
        paired_completed_independently_labeled_cases=sum(
            c.case_id in common and c.label is not None for c in benchmark.cases
        ),
        integration_recommendation=(
            "NOT JUSTIFIED: independent held-out live VLM benefit has not been established"
        ),
    )


def run(benchmark, limits, directory):
    started = time.monotonic()
    directory = safe_path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    (directory / "cache").mkdir(exist_ok=True, mode=0o700)
    safe_path(directory / "cache")
    context = sha(
        canonical(dict(manifest=benchmark.model_dump(mode="json"), limits=limits.model_dump()))
    )
    rows = []
    hashes = {}
    deadline = time.monotonic() + limits.run_seconds
    with exclusive(directory):
        budget = Budget(directory, limits, context)
        # Audit the whole selected cohort before any external request; ground truth
        # and capture/group split leakage cannot be discovered only after spending.
        for case in benchmark.cases[: limits.max_cases]:
            audited = verified_case(case)
            for image in audited[2]:
                digest = pixel_sha(image.original_rgb)
                if digest in hashes and hashes[digest] != case.split:
                    raise ValueError("Duplicate capture crosses evaluation splits")
                hashes[digest] = case.split
            del image
            del audited
        for case in benchmark.cases[: limits.max_cases]:
            verified = verified_case(case)
            for mode in ("cv_only", "vlm_only", "hybrid"):
                rows.append(assess(mode, case, verified, limits, directory, budget, deadline))
                write_json(directory / "results.json", rows)
            # Release original arrays before the next RHS loads another collection.
            del verified
        selected = Benchmark(cases=benchmark.cases[: limits.max_cases])
        summary = summarize(selected, rows)
        summary.update(
            cases=len(selected.cases),
            arms=len(rows),
            budget=budget.data,
            cv_timing_scope="CV report verification/replay, not fresh model inference",
            credential_available=bool(
                os.environ.get(
                    "OPENROUTER_API_KEY" if limits.provider == "openrouter" else "GEMINI_API_KEY"
                )
            ),
            total_wall_seconds=time.monotonic() - started,
        )
        finite_tree(summary)
        write_json(directory / "summary.json", summary)
        write_json(directory / "config.json", limits.model_dump(mode="json"))
        write_json(directory / "manifest.json", selected.model_dump(mode="json"))
    return summary
