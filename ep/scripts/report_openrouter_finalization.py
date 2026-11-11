"""Revalidate stored live evidence and report actual successes, rejections and native checks."""

import json
import sys
import tracemalloc
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ep_engine.v31.contracts import InspectionReport
from ep_engine.vlm_eval.contracts import Benchmark, Limits, Reply
from ep_engine.vlm_eval.evidence import (
    constrained_prediction,
    cv_prediction,
    pixel_sha,
    prepare,
    sha,
    validate_citations,
    verified_case,
)
from ep_engine.vlm_eval.fusion import fuse
from ep_engine.vlm_eval.runner import write_json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".test-artifacts/openrouter-finalization-20261111"


def read(path):
    return json.loads(path.read_bytes())


def require(condition):
    if not condition:
        raise ValueError("Finalization evidence verification failed")


def xml_cases(path):
    return list(ET.parse(path).getroot().iter("testcase"))  # noqa: S314 - local test receipts


def main():
    frozen = read(ROOT / ".test-artifacts/ep-v31-improvement-20261111/source-checksums.json")
    require(all(sha((ROOT / name).read_bytes()) == digest for name, digest in frozen.items()))
    photos = read(ROOT / ".test-artifacts/ep-v31-20261111/dataset-checksums.json")
    require(all(sha(Path(p["Path"]).read_bytes()).upper() == p["Hash"].upper() for p in photos))
    directory = OUT / "validated-live"
    rows = read(directory / "cold-results.json")
    accepted = next(r for r in rows if r["mode"] == "vlm_only" and r["status"] == "completed")
    config = Limits.model_validate_json((directory / "config.json").read_bytes())
    case = Benchmark.model_validate_json((directory / "manifest.json").read_bytes()).cases[0]
    verified = verified_case(case)
    prepared = prepare(case, "hybrid", config, verified)
    require(prepared["input_pixels_sha256"] == accepted["input_pixel_hashes"])
    reply = Reply.model_validate(accepted["reply"])
    validate_citations(reply, prepared)
    prepared["_artifacts"] = verified[3]
    prediction, reason = constrained_prediction(reply, "hybrid", verified[1], prepared)
    replay = dict(
        accepted,
        mode="hybrid",
        prediction=prediction,
        reason=reason,
        reasoning_scope="cv_supported_regions",
        live_inference=False,
        replay_origin="accepted_vlm_only_reply_offline_fusion_test",
    )
    combined = fuse(verified[1].inspection_id, "hybrid", verified[1], replay)
    require(not combined.confirmed_damage and not combined.physical_identity_verified)
    require(combined.payment_action == "none")
    write_json(OUT / "validated-live-reply-hybrid-replay.json", combined.model_dump(mode="json"))
    native = read(OUT / "native-complete/measurements.json")
    expected = {
        t.get("classname").replace(".", "/") + ".py::" + t.get("name")
        for t in xml_cases(ROOT / ".test-artifacts/openrouter-v31-20261111/native.xml")
    }
    require({r["node"] for r in native} == expected)
    native_passed = 0
    for index, row in enumerate(native):
        cases = xml_cases(OUT / f"native-complete/{index}/tests.xml")
        if (
            row["exit_code"] == 0
            and len(cases) == 1
            and all(
                t.find("failure") is None and t.find("error") is None and t.find("skipped") is None
                for t in cases
            )
        ):
            native_passed += 1
    require(native_passed == len(expected))
    controls = Benchmark.model_validate_json(
        (ROOT / ".test-artifacts/vlm-evaluation-20261111/manifest.json").read_bytes()
    )
    exact = []
    for c in controls.cases:
        report = InspectionReport.model_validate_json(c.cv_report.read_bytes())
        require(report.payment_action == "none")
        if c.kind == "exact_repeat":
            require(cv_prediction(report) is False)
            require(not report.cv_package.candidates and not report.cv_package.boundary_changes)
            require(not any(s.appearance_regions for s in report.surface_observations))
            exact.append(c.case_id)
    tests = {}
    for path in OUT.glob("*.xml"):
        suites = list(ET.parse(path).getroot().iter("testsuite"))  # noqa: S314 - local test XML
        tests[path.name] = {
            k: sum(float(s.get(k, 0)) for s in suites)
            for k in ("tests", "failures", "errors", "skipped", "time")
        }
    test_table = ["| Verification | Passed | Failed | Skipped |", "|---|---:|---:|---:|"]
    for filename in ("regression-final.xml", "policy.xml", "observer.xml", "native-complete.xml"):
        record = tests[filename]
        passed = record["tests"] - record["failures"] - record["errors"] - record["skipped"]
        test_table.append(
            f"|{filename}|{int(passed)}|{int(record['failures'] + record['errors'])}|"
            f"{int(record['skipped'])}|"
        )
        if filename != "native-complete.xml":
            require(record["failures"] == 0 and record["errors"] == 0)
    test_table.append(f"|Complete isolated native campaign|{native_passed}|0|0|")
    image = np.zeros((1024, 1024, 3), np.uint8)
    memory = {}
    for name, operation in (
        ("previous_tobytes", lambda: sha(image.tobytes())),
        ("buffer_hash", lambda: pixel_sha(image)),
    ):
        tracemalloc.start()
        digest = operation()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        memory[name] = dict(python_peak_bytes=peak, digest=digest)
    require(memory["previous_tobytes"]["digest"] == memory["buffer_hash"]["digest"])
    write_json(OUT / "hash-memory-control.json", memory)
    routes = read(OUT / "route-diagnostics.json")
    require(
        next(r for r in routes if r["model"].startswith("nvidia/nemotron-3.5"))[
            "provider_error_category"
        ]
        == "privacy_policy_no_eligible_endpoint"
    )
    require(
        next(r for r in routes if r["model"].startswith("dots-studio/"))["status"]
        == "synthetic_route_accepted"
    )
    initial = read(OUT / "native-isolated/measurements.json")
    late = [r for r in read(OUT / "live-final/results.json") if r.get("generation_started")]
    require(len(late) == 3 and all(r["status"] == "failed" for r in late))
    warm = read(directory / "warm-results.json")
    rejected = [read(p)["result"] for p in (directory / "rejected").glob("*.json")]
    require(len(rejected) == 1)
    table = [
        "| Arm | Status | Seconds | Input / output tokens | Reported cost |",
        "|---|---|---:|---:|---:|",
    ]
    for row in rows:
        usage = row.get("usage", {})
        cost = row.get("provider_reported_cost_usd", "N/A")
        if row["mode"] == "hybrid" and row["status"] == "failed":
            usage = rejected[0]["usage"]
            cost = rejected[0]["provider_reported_cost_usd"]
        table.append(
            f"|{row['mode']}|{row['status']}: {row['reason']}|"
            f"{row['elapsed_seconds']:.3f}|"
            f"{usage.get('promptTokenCount', 'N/A')} / {usage.get('candidatesTokenCount', 'N/A')}|"
            f"{cost}|"
        )
    rejected_reply = Reply.model_validate(rejected[0]["reply"])
    try:
        validate_citations(rejected_reply, prepared)
    except ValueError:
        rejected_citations = True
    else:
        raise ValueError("Expected rejected hybrid source citations to remain rejected")
    usage_bad = rejected[0]["usage"]
    body = f"""# EP v3.1 OpenRouter finalization: measured results

This campaign is preserved as history. See the subsequent
[bounded live-hybrid acceptance](openrouter-v31-hybrid-acceptance.md) for the updated
source-citation schema and geometric-scope result.

**One live VLM comparison passed strict JSON and source-citation validation. All
{native_passed}/{len(expected)} native checks pass with sequential process isolation.**
The hybrid live reply was correctly rejected for missing original-source citations;
the accepted VLM-only reply was separately tested through conservative CV fusion
without another API call. Independent damage accuracy remains unverified and
application integration is not justified.

## Confirmed routing cause and explicit free alternative

The configured `nvidia/nemotron-3.5-super-vl:free` is image-capable and exists.
A synthetic-text diagnostic returned HTTP 404, provider code 404 and sanitized
category `privacy_policy_no_eligible_endpoint`. Thus this configured route cannot
satisfy the required deny-collection policy. The prior 404 was a privacy-route
rejection, not proof that the model lacked vision. No raw provider error prose,
credentials or images were written into diagnostics. Only whitelisted codes and
categories leave the worker. The [model's data notice](https://openrouter.ai/nvidia/nemotron-3.5-super-vl:free)
and [routing rules](https://openrouter.ai/docs/guides/routing/provider-selection)
are consistent with that observed category.

Public and account-filtered catalogs had six free vision models. Two lacked JSON
mode; the two Gemma alternatives returned 429; DOTS accepted a synthetic route
probe with `data_collection=deny`, all price caps zero and fallbacks disabled.
The explicit selected model is `dots-studio/dots-3-note-preview:free`.
The backend `.env` was never changed. No real Gemini API call was made; removal of
its key has no effect on this OpenRouter path. Routing acceptance is not an
independent downstream privacy audit or a quality benchmark.

Four bounded synthetic route attempts and the first three authorized image attempts
remain preserved. The first DOTS image round returned two JSON replies and one
timeout. The replies failed the unchanged local contract: missing recapture guidance,
and a no-change reply containing change proposals. They were never scored as valid
model predictions or repaired to fit the schema. The corrected remote schema now
requires all fields, nonempty guidance/uncertainty and explicit safety values, with
clear empty-observation instructions for no-change/uncertain replies.

## Successful live comparison and hybrid safety

After new explicit authorization, one live synthetic schema check passed. Then the
same phone-front originals were sent in VLM-only and hybrid modes, with a total cap
of two image requests, five images maximum, reasoning disabled in the request and
the original 60-second deadline. All price caps remained zero and collection denied.

{chr(10).join(table)}

The accepted VLM-only reply used 3,940 input and 621 output tokens, with provider
reported cost $0. It described a possible screen-appearance difference, offered
lighting/different-device alternatives, supplied recapture guidance, and retained
identity=false, human-review=true and payment_action=none. This is an unverified
model opinion, not a condition label or confirmed physical damage.

The 37-second hybrid reply used {usage_bad["promptTokenCount"]} input and
{usage_bad["candidatesTokenCount"]} output tokens and reported $0, but cited crops
without including both original UUIDs in evidence_ids. The strict citation validator
rejected it. Its full CV report survived as `cv_fallback`. A final prompt/schema
refinement now explicitly requires both originals and enumerates attached source
IDs; that refinement has offline regression coverage and has not been live-retsted.

The accepted live VLM-only reply was revalidated against original pixel hashes and
citations, then passed through the current hybrid overlap checks offline. Result:
`{reason}`; combined decision `{combined.decision}` and supported change
`{combined.supported_appearance_prediction}`. Both the CV evidence and VLM opinion
remain reviewable. This is a fusion test using actual live output, not a successful
independent hybrid-model generation. Broad model boxes do not become verified regions.

The accepted reply was also read from its validated cache with no new API call:
{len(warm)} cache hit, {warm[0]["elapsed_seconds"]:.3f} seconds. This is one cache reuse
measurement, not a general speedup claim. Cache keys include provider, model, source
pixels, prompt/schema/transport revision, reasoning setting and credential scope.

## Inconclusive CV geometry and memory

Hybrid routing now permits an independent original-image VLM opinion when geometry
is inconclusive, using the same explicit consent and budgets. It attaches a geometry
warning and no unsupported CV proposals. JSON and source citations still validate.
The model opinion remains separate; its supported hybrid change is always unknown.
Fusion independently enforces this even if an upstream prediction is accidentally
positive. Physical identity and confirmed damage remain false and payment_action none.

The eight original native failures were reproduced with a roughly 20 MiB controller.
Initial minimum available RAM was {min(r["minimum_available"] for r in initial) / 2**30:.3f}
GiB, below the unchanged 1.5 GiB host reserve. The direct-model checks refused before
loading weights; launcher failures likewise returned memory_reserve. No user process
was closed or system cache purged. Once RAM recovered, all eight passed in isolated
processes. A subsequent shared-process run passed 15 and refused two child workers
at memory_reserve; retaining the parent Torch/CUDA process increases the resource
envelope. Fresh-process isolation avoids that retained parent working set.

The complete isolated campaign verified the exact original 17 test identities:
**{native_passed} passed**. Controller peak was
{max(r["controller_rss"] for r in native) / 2**20:.1f} MiB, maximum measured child-tree
working set {max(r["peak_child_rss"] for r in native) / 2**30:.3f} GiB, and minimum sampled
available RAM {min(r["minimum_available"] for r in native) / 2**30:.3f} GiB. Individual
process execution totaled {sum(r["seconds"] for r in native):.3f} seconds. Failed
and successful XML/measurements remain separate; shared-process failure is not hidden.

Two avoidable wrapper allocations were removed without touching CV: collection arrays
are released before loading the next case (including the audit loop's last image),
and contiguous RGB arrays are hashed through their buffer instead of tobytes().
A 3 MiB generated control measured Python allocation peaks of
{memory["previous_tobytes"]["python_peak_bytes"]} bytes before and
{memory["buffer_hash"]["python_peak_bytes"]} bytes after, with identical digests.
These are host-memory improvements, not a GPU speedup or lowered memory requirement.

## Verification, preservation and readiness

{chr(10).join(test_table)}

The shared-process `native-complete.xml` refusals are preserved alongside the passing
isolated campaign. All early XML, process measurements and full test records are
retained in the private artifact directory and `acceptance.json`.
The opt-in synthetic data policy checks are run separately from general regression.
All {len(exact)} frozen exact-repeat controls retain scoped negative CV predictions
and zero coarse/boundary/original-tile proposals. All {len(controls.cases)} archived
strict reports retain payment_action none. Current fusion tests cover unverified
identity, disagreement, missing credentials, financial invariance, prompt/citation
rules, disabled-provider silence, caching, retries and timeouts.

All {len(frozen)} frozen EP source files and {len(photos)} original photograph hashes
match. CV models, thresholds, contracts, original evidence, application, payments,
Supabase and Git history are unchanged. No heavyweight download occurred.

**Suitable for bounded private standalone engineering review; application integration
is not justified.** There are no independently reviewed condition labels, no paired
validated live hybrid benefit, and no calibrated confidence or physical identity.
The tested free preview route may change or disappear. Local privacy/cost controls
and graceful fallback remain mandatory. The final citation-request refinement is
offline verified only; it has not been used to relabel the rejected live reply.

See [architecture and operator instructions](openrouter-v31.md). Actual reports and
receipts are private under `.test-artifacts/openrouter-finalization-20261111/`:
`validated-live/phone-front-vlm_only.json`, `validated-live/phone-front-hybrid.json`,
and `validated-live-reply-hybrid-replay.json`. Reproduction of native checks:

```powershell
& $epPython -B scripts/verify_native_isolated.py --campaign complete --all
& $epPython -B scripts/report_openrouter_finalization.py
```

Existing API campaign ledgers are exhausted. Rerunning diagnostics cannot silently
reset them; new image requests require new bounded authorization.
"""
    body = body.replace("live-retsted", "live-retested")
    (ROOT / "docs/openrouter-v31-finalization.md").write_text(body, "utf-8")
    write_json(
        OUT / "acceptance.json",
        dict(
            cv_source_preserved=True,
            original_photos_preserved=True,
            independent_condition_labels=sum(c.label is not None for c in controls.cases),
            native_passed=native_passed,
            native_expected=len(expected),
            live_vlm_only_accepted=1,
            live_hybrid_accepted=0,
            live_hybrid_citations_rejected=rejected_citations,
            offline_hybrid_replay_reason=reason,
            tests=tests,
            integration_ready=False,
        ),
    )
    write_json(
        OUT / "source-checksums.json",
        {
            str(p.relative_to(ROOT)): sha(p.read_bytes())
            for p in (ROOT / "ep_engine/vlm_eval").glob("*.py")
        },
    )
    print(
        json.dumps(
            dict(
                native_passed=native_passed,
                native_expected=len(expected),
                successful_live_vlm_comparisons=1,
                integration_ready=False,
            )
        )
    )


if __name__ == "__main__":
    main()
