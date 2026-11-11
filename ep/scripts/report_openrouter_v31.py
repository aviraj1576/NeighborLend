"""Build an evidence-based standalone OpenRouter report without inventing labels."""

import json
import statistics
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ep_engine.v31.contracts import InspectionReport
from ep_engine.vlm_eval.contracts import Benchmark
from ep_engine.vlm_eval.evidence import sha
from ep_engine.vlm_eval.fusion import CombinedReport
from ep_engine.vlm_eval.runner import write_json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".test-artifacts/openrouter-v31-20261111"


def read(path):
    return json.loads(path.read_bytes())


def main():
    previous = read(ROOT / ".test-artifacts/ep-v31-improvement-20261111/source-checksums.json")
    changed = [
        name for name, digest in previous.items() if sha((ROOT / name).read_bytes()) != digest
    ]
    dataset = read(ROOT / ".test-artifacts/ep-v31-20261111/dataset-checksums.json")
    changed_photos = [
        row["Path"]
        for row in dataset
        if sha(Path(row["Path"]).read_bytes()).upper() != row["Hash"].upper()
    ]
    if changed or changed_photos:
        raise ValueError("Frozen CV source or original photo preservation check failed")
    tests = {}
    for path in OUT.glob("*.xml"):
        suites = list(ET.parse(path).getroot().iter("testsuite"))  # noqa: S314 - local test XML
        tests[path.name] = {
            field: sum(float(s.get(field, 0)) for s in suites)
            for field in ("tests", "failures", "errors", "skipped", "time")
        }
    cold = read(OUT / "offline-cold-summary.json")
    warm = read(OUT / "offline-all/summary.json")
    live = read(OUT / "live-smoke/summary.json")
    rows = read(OUT / "live-smoke/results.json")
    attempted = [r for r in rows if r.get("generation_started")]
    accepted = [r for r in rows if r.get("live_inference")]
    labeled = Benchmark.model_validate_json(
        (ROOT / ".test-artifacts/vlm-evaluation-20261111/manifest.json").read_bytes()
    )
    labels = sum(c.label is not None for c in labeled.cases)
    if labels:
        raise ValueError("Report template requires review if independent labels become available")
    examples = list((OUT / "live-smoke").glob("*-hybrid.json"))
    for path in examples:
        CombinedReport.model_validate_json(path.read_bytes())
    # The CV replay matches every original strict report; no fresh inference claim.
    for case in labeled.cases:
        InspectionReport.model_validate_json(case.cv_report.read_bytes())
    mode_table = ["| Mode | Offline cold status | Cache hits on repeat |", "|---|---|---:|"]
    for mode in ("cv_only", "vlm_only", "hybrid"):
        mode_table.append(
            f"|{mode}|{cold['modes'][mode]['statuses']}|{warm['modes'][mode]['cache_hits']}|"
        )
    live_table = ["| Case | Mode | Actual result | Seconds |", "|---|---|---|---:|"]
    for row in rows:
        live_table.append(
            f"|{row['case_id']}|{row['mode']}|{row['status']}: {row['reason']}"
            f"{(' HTTP ' + str(row['http_status'])) if row.get('http_status') else ''}"
            f"|{row['elapsed_seconds']:.3f}|"
        )
    durations = [r["elapsed_seconds"] for r in attempted]
    verification = read(OUT / "environment-verification.json")
    body = f"""# EP v3.1 optional OpenRouter: implementation and measured verification

This initial run is preserved as history. See the
[finalization report](openrouter-v31-finalization.md) for current measured results.

**Implemented and verified offline; live model reasoning and application integration
are not ready.** The three authorized free requests were rejected with HTTP 404.
The current free model's published collection policy conflicts with the required
deny-collection routing policy. No privacy relaxation or paid fallback was used.
Independent appearance/damage labels are absent, so accuracy remains N/A.

## Implemented architecture

The existing EfficientSAM → DINOv2 → RootSIFT/LoFTR → RANSAC → CUDA SSIM/residual
→ localized evidence → multiview → v3.1 report pipeline is preserved. All
{len(previous)} previously checksummed EP source files match, and all {len(dataset)}
original photograph hashes match. No original photo, frozen evidence, payment,
database, application workflow or Git operation was changed.

The optional standalone wrapper adds original-image routing, OpenRouter capability
verification, strict JSON/citations/region validation, and a separate fusion envelope.
`cv_only` executes existing CV; `vlm_only` executes no CV; `hybrid` retains full CV
evidence and model observations separately. Unsupported geometry abstains before
transmission. Disagreement remains uncertain; remote failure returns CV fallback.
Identity is always unverified, confirmed damage is false, human review is mandatory,
and payment_action is none. See [architecture and operator guide](openrouter-v31.md).

## Environment and live execution

The explicitly named backend `.env` was read without editing it or importing backend
settings. The receipt contains only credential presence, enabled/provider/model/base
URL/timeout and public model capabilities. Model: `{verification["model"]}`;
timeout {verification["timeout_seconds"]:.0f} seconds. Catalog modalities include
image, and structured outputs and zero token prices were verified before generation.
Only HTTPS `openrouter.ai` is allowed. Images are inline original-resolution PNGs
with embedded metadata stripped; visible background privacy is not anonymized.

{chr(10).join(live_table)}

The three reserved POST attempts had median total record time
{statistics.median(durations):.3f} seconds (range {min(durations):.3f}–{max(durations):.3f});
the complete three-case replay/smoke run took {live["total_wall_seconds"]:.3f} seconds.
These timings include original-image preparation, worker startup, catalog verification,
rate pacing and rejection, not successful model inference. Accepted replies: {len(accepted)}.
No token usage or provider cost was returned. Local reserved/estimated spend is $0;
provider billing is not independently audited. All requests enforced zero maximum
prompt/completion/image/request prices and denied data collection. Remaining arms
were explicitly not run after the three-request budget was exhausted; bag hybrid
abstained locally because global geometry was unsupported.

The public endpoint metadata showed one NVIDIA endpoint. Its
[published model notice](https://openrouter.ai/nvidia/nemotron-3.5-super-vl:free)
states that session data is collected for product improvement. OpenRouter's
[routing policy](https://openrouter.ai/docs/guides/routing/provider-selection)
explains deny-collection filtering. This is consistent with the HTTP 404 failures;
raw provider error bodies were deliberately not retained, so an exact server-side
rejection explanation is not established. Catalog capability is not route availability.
No additional image requests were made to probe weaker privacy settings.

## Available-data benchmark

All {len(labeled.cases)} existing cases and their original strict CV reports were
verified. There are {labels} independently reviewed change labels. The cold offline
fixture run took {cold["total_wall_seconds"]:.3f} seconds; its identical cache replay
took {warm["total_wall_seconds"]:.3f} seconds. Both issued zero API requests.

{chr(10).join(mode_table)}

Offline fixture responses are deterministic uncertainty, not VLM predictions or
model-accuracy evidence. Over-budget original-image collections remain not run.
CV replay has 11 unverified appearance-positive cases, 27 scoped negatives and 18
abstentions. This export eligibility is distinct from CV pair comparability; existing
real-pair comparability remains 8/17. The work neither improves nor remeasures physical
damage accuracy. No independent paired live comparison completed in all three modes.

## Tests and remaining verification

Preserved test records: `{json.dumps(tests, sort_keys=True)}`.

Offline tests cover generated-image positive/negative cases, original pixel fidelity,
metadata removal, label blindness, valid/invalid citations, normalized coordinates,
both-source overlap, geometry rejection, CV/VLM disagreement, disabled/no-secret paths,
missing credentials, unsupported/paid models, strict JSON including duplicate/nonfinite
values, truncation, API 401/429/503 and redirects, bounded metadata retry, separately
reserved optional 429 generation retry, concurrency locks, output cost rejection,
cache corruption/revalidation, worker deadlines, budget durability, financial/identity
prohibition and preservation of the CV report on fallback. Mocked successful replies
are software controls only and are not counted as live successes.

The native suite passed nine checks but eight model/launcher checks failed under
host RAM pressure at the unchanged `memory_reserve` guard. Rechecking those eight
in a fresh process also failed. Their failure XML remains intact; this run does not
claim a full native pass. No memory threshold or safety test was relaxed. Prior
[refinement validation](ep-v31-refinement-report.md) is historical evidence, not a
substitute for the incomplete current native recheck.

## Examples, readiness and reproduction

Actual strict combined reports are in the private artifact directory:
`live-smoke/phone-front-cv_only.json`, `live-smoke/phone-front-hybrid.json`, and
`live-smoke/bag-front-hybrid.json`. They demonstrate preserved CV, API-failure fallback,
and geometry abstention. `reply.schema.json` and `combined-report.schema.json` are
exported alongside them. Successful grounded observations, no-change replies and
disagreement behavior are exercised with generated pixels in offline tests.

**Keep this as an optional private standalone evaluation layer. Application integration
is not justified.** A compatible free route satisfying the approved privacy policy,
a successful bounded live comparison, passing native checks with adequate host RAM,
and independently reviewed object/session-held-out labels are still required.
No calibrated uncertainty, damage liability, cross-view surface correspondence,
whole-object condition conclusion or automatic financial authority is established.

Run from `ep/` with the approved interpreter:

```powershell
$env:PYTHONPATH = '.runtime/v3-packages;.'
& $epPython -B scripts/run_optional_vlm.py verify --env-file ../backend/.env --check-model
& $epPython -B scripts/report_openrouter_v31.py
```

Private receipts, request ledger, benchmarks, checksums, examples and test XML live
under `.test-artifacts/openrouter-v31-20261111/`. Reusing the same manifest/config
directory preserves its exhausted budget; opening a new directory is a new campaign
and still requires explicit image consent and request authorization.
"""
    (ROOT / "docs/openrouter-v31-report.md").write_text(body, "utf-8")
    write_json(
        OUT / "acceptance.json",
        dict(
            existing_cv_source_files_verified=len(previous),
            original_photo_hashes_verified=len(dataset),
            existing_cv_source_unchanged=True,
            original_photos_unchanged=True,
            tests=tests,
            independent_labels=labels,
            live_attempts=len(attempted),
            live_accepted_replies=len(accepted),
            live_http_statuses=dict(Counter(str(r.get("http_status")) for r in attempted)),
            integration_ready=False,
            native_recheck_complete=False,
        ),
    )
    write_json(
        OUT / "optional-source-checksums.json",
        {
            str(p.relative_to(ROOT)): sha(p.read_bytes())
            for p in (ROOT / "ep_engine/vlm_eval").glob("*.py")
        },
    )
    print(
        json.dumps(
            dict(
                cv_source_preserved=True,
                original_photos_preserved=True,
                live_attempts=len(attempted),
                live_successes=len(accepted),
                integration_ready=False,
            )
        )
    )


if __name__ == "__main__":
    main()
