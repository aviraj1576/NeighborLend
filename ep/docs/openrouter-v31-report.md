# EP v3.1 optional OpenRouter: implementation and measured verification

This initial run is preserved as history. See the
[finalization report](openrouter-v31-finalization.md) for the confirmed 404 category,
compatible free route, accepted live comparison, updated routing and native rechecks.

**Implemented and verified offline; live model reasoning and application integration
are not ready.** The three authorized free requests were rejected with HTTP 404.
The current free model's published collection policy conflicts with the required
deny-collection routing policy. No privacy relaxation or paid fallback was used.
Independent appearance/damage labels are absent, so accuracy remains N/A.

## Implemented architecture

The existing EfficientSAM → DINOv2 → RootSIFT/LoFTR → RANSAC → CUDA SSIM/residual
→ localized evidence → multiview → v3.1 report pipeline is preserved. All
58 previously checksummed EP source files match, and all 34
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
URL/timeout and public model capabilities. Model: `nvidia/nemotron-3.5-super-vl:free`;
timeout 60 seconds. Catalog modalities include
image, and structured outputs and zero token prices were verified before generation.
Only HTTPS `openrouter.ai` is allowed. Images are inline original-resolution PNGs
with embedded metadata stripped; visible background privacy is not anonymized.

| Case | Mode | Actual result | Seconds |
|---|---|---|---:|
|phone-front|cv_only|completed: replayed_verified_cv_evidence|0.000|
|phone-front|vlm_only|failed: provider_rejected HTTP 404|7.828|
|phone-front|hybrid|failed: provider_rejected HTTP 404|7.750|
|repeat-phone-front|cv_only|completed: replayed_verified_cv_evidence|0.000|
|repeat-phone-front|vlm_only|failed: provider_rejected HTTP 404|7.485|
|repeat-phone-front|hybrid|not_run: request_budget_exhausted|0.671|
|bag-front|cv_only|completed: replayed_verified_cv_evidence|0.000|
|bag-front|vlm_only|not_run: request_budget_exhausted|0.906|
|bag-front|hybrid|completed: cv_geometry_gate_abstained_without_api|0.000|

The three reserved POST attempts had median total record time
7.750 seconds (range 7.485–7.828);
the complete three-case replay/smoke run took 26.047 seconds.
These timings include original-image preparation, worker startup, catalog verification,
rate pacing and rejection, not successful model inference. Accepted replies: 0.
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

All 56 existing cases and their original strict CV reports were
verified. There are 0 independently reviewed change labels. The cold offline
fixture run took 101.031 seconds; its identical cache replay
took 132.000 seconds. Both issued zero API requests.

| Mode | Offline cold status | Cache hits on repeat |
|---|---|---:|
|cv_only|{'completed': 56}|0|
|vlm_only|{'not_run': 3, 'offline_fixture': 53}|53|
|hybrid|{'completed': 18, 'not_run': 2, 'offline_fixture': 36}|36|

Offline fixture responses are deterministic uncertainty, not VLM predictions or
model-accuracy evidence. Over-budget original-image collections remain not run.
CV replay has 11 unverified appearance-positive cases, 27 scoped negatives and 18
abstentions. This export eligibility is distinct from CV pair comparability; existing
real-pair comparability remains 8/17. The work neither improves nor remeasures physical
damage accuracy. No independent paired live comparison completed in all three modes.

## Tests and remaining verification

Preserved test records: `{"native-recheck.xml": {"errors": 0.0, "failures": 8.0, "skipped": 0.0, "tests": 8.0, "time": 10.125}, "native.xml": {"errors": 0.0, "failures": 8.0, "skipped": 0.0, "tests": 17.0, "time": 14.815}, "policy.xml": {"errors": 0.0, "failures": 0.0, "skipped": 0.0, "tests": 2.0, "time": 0.11}, "regression-final.xml": {"errors": 0.0, "failures": 0.0, "skipped": 2.0, "tests": 326.0, "time": 50.51}, "regression.xml": {"errors": 0.0, "failures": 0.0, "skipped": 2.0, "tests": 324.0, "time": 55.358}, "tests-first.xml": {"errors": 0.0, "failures": 1.0, "skipped": 0.0, "tests": 46.0, "time": 10.215}, "tests-targeted.xml": {"errors": 0.0, "failures": 0.0, "skipped": 0.0, "tests": 46.0, "time": 18.523}}`.

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
