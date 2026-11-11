"""Build the actual standalone benchmark report; never turn model output into labels."""

import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ep_engine.vlm_eval.evidence import sha
from ep_engine.vlm_eval.runner import write_json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".test-artifacts/vlm-evaluation-20261111"


def read(path):
    return json.loads(path.read_bytes())


def main():
    summaries = {}
    records = {}
    for name in (
        "disabled-final",
        "offline-fixture",
        "live-free-pilot",
        "live-free-current",
        "free-diagnostic",
        "live-free-final",
    ):
        directory = OUT / name
        if (directory / "summary.json").exists():
            summaries[name] = read(directory / "summary.json")
            records[name] = read(directory / "results.json")
    previous = read(ROOT / ".test-artifacts/ep-v31-improvement-20261111/source-checksums.json")
    changed = [p for p, digest in previous.items() if sha((ROOT / p).read_bytes()) != digest]
    if changed:
        raise ValueError("Existing CV/application EP source changed during standalone harness work")
    tests = {}
    for path in OUT.glob("*.xml"):
        suites = list(ET.parse(path).getroot().iter("testsuite"))  # noqa: S314 - local test XML
        tests[path.name] = {
            field: sum(float(s.get(field, 0)) for s in suites)
            for field in ("tests", "failures", "errors", "skipped", "time")
        }
    live = summaries.get("live-free-final", {})
    table = ["| Case | CV-only | VLM-only | Hybrid |", "|---|---|---|---|"]
    pilot = records.get("live-free-final", [])
    for case in ("phone-front", "repeat-phone-front", "bag-front"):
        values = []
        for mode in ("cv_only", "vlm_only", "hybrid"):
            row = next((r for r in pilot if r["case_id"] == case and r["mode"] == mode), {})
            result = (
                "appearance difference"
                if row.get("prediction") is True
                else "no difference in assessed scope"
                if row.get("prediction") is False
                else "abstained"
            )
            values.append(f"{row.get('status', 'not run')}: {result}")
        table.append("|" + case + "|" + "|".join(values) + "|")
    counts = {
        name: dict(Counter(r.get("reason", "unspecified") for r in rows))
        for name, rows in records.items()
    }
    body = f"""# EP v3.1 standalone VLM evaluation: measured report

**Integration is not justified.** The existing available collection has zero
independently reviewed physical-condition or appearance-change labels. The live
pilot is an unlabeled engineering experiment. No damage precision, recall, F1,
localization accuracy or physical-identity accuracy can be reported.

## Executed comparisons

The prepared manifest binds all 56 existing cases to original source-resolution
captures and the refined v3.1 reports. The CV architecture, existing EP source files,
application, payments and databases were preserved. No Git command or operation
was performed. Existing CV comparability remains 8/17 real pairs; the harness has
stricter eligibility for exporting observations and does not change that outcome.

CV-only is verified evidence replay, not fresh model inference or a neural latency
benchmark. VLM-only sees no CV output. Hybrid sees the same original pixels plus
verified CV evidence and cannot override geometry, coverage or positive CV evidence.

{chr(10).join(table)}

Every appearance result above remains unverified. A negative is restricted to
assessed visible scope; no result establishes physical identity, physical damage
causation, liability or payment authority. The VLM receives source citations and
normalized boxes, but correct-looking citations do not independently validate its
visual interpretation. Only a future independent labeled study can establish benefit.

## Free-tier API execution

The user explicitly authorized the three named image pairs to Google's Gemini API,
confirmed that the project has billing disabled, and approved the images for unpaid
service processing. No paid fallback or billing change was made. All executed live
configs use zero token prices, a zero-dollar budget and finite per-campaign request caps.
Billing-disabled status is operator-confirmed, not independently verifiable from
an API key. Cost records are local estimates, not a provider invoice.

The first Gemini 2.5 Flash-Lite attempt was rejected at token preflight. A separate
synthetic-text token-count diagnostic returned HTTP 404 and explained that the model
is unavailable to new users, recommending Gemini 3.5 Flash-Lite. Model metadata alone
had returned HTTP 200 and was insufficient as an availability check. The replacement
passed synthetic token counting before the private pilot. Its free tier is documented
by [Google pricing](https://ai.google.dev/gemini-api/docs/pricing).

The historical 2.5 rejection ledger remains intact. No generation was issued after
a failed preflight. The replacement pilot uses its own bounded ledger; no automatic
retry, provider switching or paid upgrade exists in the harness. Private images and
their model outputs are subject to Google's unpaid-service terms, explicitly approved
by the user. See [data terms](https://ai.google.dev/gemini-api/terms).

The first six 3.5 generations returned JSON but failed local validation. Their raw
outputs were not retained, so a shared cause across all six is not established.
One subsequently authorized diagnostic captured a 0–1000 coordinate response,
which correctly failed the mandatory 0–1 unit checks. Five remaining authorized
requests with remote numeric constraints returned HTTP 400 and no model replies.
The final compact remote schema keeps complete local validation and is verified
offline only. No additional live requests beyond the authorized allowance were made.

Live final summary: `{json.dumps(live, sort_keys=True)}`.
The [OpenRouter follow-up](openrouter-v31-report.md) contains current wrapper,
provider, regression and native-check results; the records here are historical.

## Offline and safety benchmarks

The complete CV-only cohort and offline fixture cohort both use the same 56 cases.
Offline fixtures return deterministic uncertainty and are excluded from VLM accuracy.
The fixture run tests original-image export preparation, citations, geometry gates,
resource limits and cache persistence; it is not a local VLM or model benchmark.
Over-budget/deadline-skipped requests remain explicitly not run, not successful.

Sanitized per-campaign reason counts: `{json.dumps(counts, sort_keys=True)}`.

Test records (including preserved early failures): `{json.dumps(tests, sort_keys=True)}`.
The final regression suite excludes neural inference markers because this change
does not modify the established CV architecture or model code. Dedicated tests cover
original-pixel fidelity, metadata removal, label blindness, content hashes, invalid
citations, geometry/overlap in both sources, free-only admission, credential handling,
truncated output, redirects/response bounds, worker deadlines, usage, ledger fsync,
interrupted-write recovery, cache corruption, split leakage and abstention metrics.

A real Windows DELETE-sharing refusal during an early benchmark checkpoint exposed
an avoidable rename dependency. Diagnostic JSON snapshots now use one locked writer;
the authoritative spend reservations are append-only, fsynced before any remote call.
A failed snapshot cannot refund a reservation. A torn ledger fails closed. Early
test/benchmark failures are retained separately and are not reported as final passes.

## Decision and remaining requirements

**Keep the standalone harness; do not integrate a VLM into the application yet.**
There are no independently labeled cases, no complete damage-detection study and
no calibrated uncertainty. The pilot's sample is deliberately small and selected
for engineering behaviors, not a representative holdout. Cross-view surfaces,
nonrigid items, lighting/reflections and identity remain unresolved.

Before considering integration, collect independently reviewed matched unchanged,
changed, lighting, pose, occlusion and different-instance cases. Lock object/session
splits, annotations, prompts/model versions and decision criteria before evaluation.
Measure paired error counts, assessed coverage/abstention, localization, latency and
cost with object-group uncertainty intervals. Do not infer damage from unlabeled
appearance differences or use provider availability as quality evidence.

## Reproduction

See [operator documentation](vlm-evaluation.md) and
[free-only configuration](vlm-evaluation-live-config.example.json).
All private manifests, sanitized outcomes, cache entries, schemas, test XML and
reservation ledgers are under `.test-artifacts/vlm-evaluation-20261111/`.
Keys and original-image bytes are not copied into report/cache files.
The supplied key is read only from the explicitly named local key file.
"""
    (ROOT / "docs/vlm-evaluation-report.md").write_text(body, "utf-8")
    write_json(
        OUT / "acceptance.json",
        dict(
            cv_architecture_unchanged=not changed,
            independently_labeled_cases=0,
            physical_damage_accuracy=None,
            tests=tests,
            campaigns=summaries,
            integration_recommendation="NOT JUSTIFIED",
        ),
    )
    write_json(
        OUT / "harness-source-checksums.json",
        {
            str(p.relative_to(ROOT)): sha(p.read_bytes())
            for p in (ROOT / "ep_engine/vlm_eval").glob("*.py")
        },
    )
    print(
        json.dumps(
            dict(
                campaigns=list(summaries),
                cv_architecture_unchanged=True,
                independently_labeled_cases=0,
                integration_recommendation="NOT JUSTIFIED",
            )
        )
    )


if __name__ == "__main__":
    main()
