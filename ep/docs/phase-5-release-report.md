# Phase 5 release report

Date: 2026-11-08, Asia/Calcutta. Release status: **PASS — controlled software readiness**.
Scope is controlled AI-subsystem software readiness, not real-world accuracy, live Gemini
acceptance, production deployment approval or completed NeighborLend application integration.

## Confirmed gaps and corrections

The existing implementation was reused. No replacement model, new dependency, training,
threshold tuning, architecture rewrite, frontend/backend integration or live API call occurred.

| Gap | Evidence and final behavior |
| --- | --- |
| No single native API-to-report acceptance test | New `test_native_api_to_private_review_report` runs secure uploads, inspection creation, the actual CV worker entrypoint/default hidden subprocess, genuine pinned EfficientSAM/DINOv2, geometry/change stages, assessment worker entrypoint, mocked official Gemini HTTP, fusion, private persistence and authenticated restart retrieval. |
| Worker source/config substitution | Test-first injections showed that changed thresholds, source dimensions and processing dimensions were accepted. CV commit/read now binds the source/config manifest to stored evidence and the queued request. Processing scale and quality dimensions are validated. Changed originals/forged stored thresholds block results, artifacts and assessment submission. |
| Duplicate record inflation | CV packages reject duplicate candidate IDs and duplicate before/after pair records. Distinct observations remain separately cited; there is no confidence-vote count. |
| Unresolved overlapping conflicts | Shared-frame overlapping observations now carry a not-independent-confirmations limitation. Positive versus no-change/artifact conflicts force an inconclusive report while retaining both cited observations for human review. No physical correspondence is guessed between unrelated captures. |

The initial focused reproduction had four failures and one pass; the repeated-positive
assertion was tightened to require the specific independence warning. All regressions now
pass. Existing valid schema 1.0 evidence/inspection, schema 2.0 CV and schema 4.0 assessment
contracts are preserved; invalid metadata is rejected more strictly. Source membership,
roles, hashes, geometry, artifact UUIDs, crop boxes and citation scope are checked across
stage boundaries. Parent inspections retain Phase 1 `created`/unavailable semantics.

## Exact changed files

Application code:

- `ep_engine/cv/contracts.py`: coordinate consistency and duplicate-record guards.
- `ep_engine/cv/service.py`: approved manifest/config checks at commit and retrieval.
- `ep_engine/assessment/engine.py`: repeated-region and conflicting-observation fusion.

Tests:

- `tests/integration/test_release_native.py`: complete native release acceptance.
- `tests/integration/test_cv_service.py`: worker and persisted-manifest tampering/staleness.
- `tests/unit/test_assessment_engine.py`: repeated/conflicting observations and duplicate records.

Final documents only:

- `docs/phase-5-release-report.md`.
- `docs/phase-5-integration-contract.md`.
- `docs/phase-5-handoff.md`.

Generated logs, JUnit/coverage files, model caches and private synthetic acceptance cases
remain under EP. Existing untracked work and historical image reports are preserved. Git
reported no tracked changes outside EP; all edits made in this milestone target EP paths.

## Executed verification

Interpreter: `D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe`. All commands run
from `ep/`, natively on Windows; no package/environment/OS modification was performed.

```powershell
$epPython = 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:EP_SYNTHETIC_ONLY = '1'
& $epPython -B -m pytest tests/integration/test_cv_service.py tests/integration/test_phase34_integration.py tests/unit/test_assessment_engine.py tests/unit/test_gemini_provider.py tests/security/test_cv_output_validation.py -q --tb=short --junitxml=.test-artifacts/phase5-targeted.xml
$env:EP_RUN_CONTROLLED_CV = '1'
& $epPython -B -m pytest tests/integration/test_release_native.py -q --tb=short --junitxml=.test-artifacts/phase5-native.xml
& $epPython -B scripts/verify.py all --synthetic-only
& $epPython -B scripts/verify.py coverage --synthetic-only
& $epPython -B scripts/verify.py lint
& $epPython -B scripts/verify.py format
```

| Gate | Executed result |
| --- | --- |
| Focused CV/assessment/Gemini/security regression | 95 passed, 0 failed/errors/skipped; 20.79 s. |
| Dedicated native API-to-report acceptance | 2 passed, 0 failed/errors/skipped; 26.47 s. |
| Complete synthetic-only regression | 214 passed, 0 failed/errors, 2 documented skips; 141.96 s. |
| Complete coverage gate | 214 passed, 0 failed/errors, 2 documented skips; 189.20 s; **93.61% combined coverage**, passing the unchanged 85% gate. |
| Ruff lint | Passed. |
| Ruff formatting | Passed; all 88 Python files formatted. |

Final coverage-run categories: unit 115 passed; integration 51 passed/2 skipped;
security 31 passed; regression 17 passed. Actual combined coverage is
93.61119561910557% (2,445/2,557 executable statements and 632/730 branches covered).
No required software test is blocked; independently labeled accuracy validation remains
blocked as described below. Dedicated acceptance JUnit cases are
`test_native_api_to_private_review_report[cuda-True-2]` (15.751 s) and
`test_native_api_to_private_review_report[cpu-False-1]` (10.424 s), including fixture overhead.

Final logs: `.test-artifacts/phase5-{targeted,native,all,coverage}.log`; JUnit reports
`phase5-targeted.xml`, `phase5-native.xml`, `all.xml`, `coverage.xml`. Coverage output is
`.test-artifacts/coverage.json` and `coverage-html/index.html`, including all `ep_engine`
code under the unchanged 85% combined gate. No newly implemented code was excluded.
Two skips are existing `test_cv_real.py` cases that use a separate bundled photograph;
synthetic-only policy intentionally skips them. Focused runs had one existing Starlette
HTTPX deprecation warning; full regression had seven warnings, including existing optional
xFormers notices. No dependency changes were made to suppress warnings.

Test-source scan found excluded path strings only in denial guards/tests. The pytest
audit hook and child data policy remain enabled. No excluded photographs or derived
exploratory artifacts were read, enumerated or used as validation evidence.

## Genuine native integration and measurements

Exact test: `tests/integration/test_release_native.py::test_native_api_to_private_review_report`.
Both existing CLI entrypoints are invoked through their real `main()` functions with
environment-only local fixture authorization. The CV entrypoint launches the actual
hidden native subprocess; no CV service/model/geometry output is substituted. Only the
Gemini HTTP client transport is replaced. Both cases reopen the actual private databases
and retrieve the persisted report through authenticated FastAPI requests.

Fixtures: generated 256x256 RGB images, background 230, central `[48:208,48:208]` texture
from NumPy seeds 42 and 43 in range `[30,170)`, explicit normalized target box
`(0.16,0.16,0.84,0.84)`. CUDA paints return pixels `[105:135,110:140]` black in two views.
CPU uses one byte-identical before/after pair. These are controlled software scenarios,
not photographs, physical scratches/dents, independent captures or model-accuracy labels.

Focused acceptance measurements (single observations, outside coverage instrumentation):

| Measurement | CUDA supported change | CPU unchanged |
| --- | ---: | ---: |
| Before / after images | 2 / 2 | 1 / 1 |
| Comparable selected pairs | 2 | 1 |
| Appearance candidates | 2 | 0 |
| Private PNG artifacts | 20 | 8 |
| Mock Gemini HTTP requests | 1 | 0 |
| Final analytical status | human_review_required | no_visible_change |
| CV worker wall seconds | 13.5496 | 9.6486 |
| CV pipeline seconds | 11.2494 | 8.0384 |
| Assessment worker wall seconds | 0.3895 | 0.0818 |
| Upload-to-restart/retrieval wall seconds | 15.4895 | 10.4182 |
| EfficientSAM load seconds | 0.9425 | 0.4905 |
| DINOv2 load seconds | 0.7918 | 0.7317 |
| CV child RSS bytes at measurement | 1,064,275,968 | 752,844,800 |
| CV child peak working set bytes | 1,086,173,184 | 1,076,355,072 |
| Peak Torch CUDA allocation bytes | 483,944,448 | 0 |

CUDA stage seconds: quality 0.0090, segmentation 10.0726, features 1.0889, matching 0.0159,
alignment 0.0348, candidates 0.0258. Segmentation includes first Torch/model initialization.
CPU stage seconds: 0.0028, 7.0087, 0.9892, 0.0124, 0.0136, 0.0103 respectively. This is a
functional baseline under varying load/cache conditions, not a performance improvement,
throughput estimate, percentile latency or precision measurement. Coverage/final-suite
timings include additional instrumentation/contention and are not comparable speed trials.
No performance-sensitive code was optimized from these isolated observations.

Hardware: native Windows, RTX 4060 Laptop GPU, existing CUDA-enabled Torch environment.
Preflight before the dedicated test reported 2.55 GiB free host RAM and 7,757 MiB free
VRAM. Before final regression, free RAM was 5.57 GiB. Per-model reserve checks remained
enabled and native execution succeeded without lowering guards or closing programs.
CPU is explicit supported execution; unsafe CUDA/OOM conditions still fail safely.
Torch peak measures allocator-tracked tensors, not total driver/device memory. Child RSS
excludes API/pytest memory; no whole-system peak or long-running stability claim is made.
Child termination and existing model cleanup prevent cross-job retained model state.

Immutable focused-case evidence locations:

- CUDA: `.test-artifacts/phase5-release/cuda-64e481ab-a671-4d10-98d5-1069cbe61976/`.
- CPU: `.test-artifacts/phase5-release/cpu-aeb85745-3def-445b-ab73-9640d306e00e/`.

Each contains `results.json`, `cv-package.json`, key-free `gemini-manifests.json`, and
`private/` with original/normalized evidence, actual SQLite databases and
`cv/artifacts/{cv_run_id}/{artifact_id}.png`. Final gate case pointers are
`.test-artifacts/phase5-release/latest-{cuda,cpu}.json`; unique case directories are retained.
The focused CUDA overlay was visually inspected and encloses the synthetic black patch.
All artifact hashes/dimensions and source/crop frame mappings passed automated checks.
The stored provider name identifies Gemini wire compatibility; `mocked_http_only=true`
in case metadata and explicit mock explanations identify external responses as fixtures,
never genuine Gemini inference. No provider key or HTTP header is persisted.

## Failure propagation, security and integration boundary

The final suite covers corrupt/malicious uploads, role/rental authorization, source/hash
tampering, quality/segmentation rejection, weak matching, unstable geometry, insufficient
overlap, model corruption/OOM/unavailable CUDA, cancellation/timeout, worker interruption,
exclusive locking, missing/corrupt artifacts, rollback and stale source/result rejection.
Unsupported CV regions cannot reach Gemini. Invalid/refused/truncated provider output,
invented/cross-source citations and financial fields cannot enter accepted findings.
Provider failures produce explicitly inconclusive reports without fabricated observations;
failed jobs expose no successful result. Completed-report status is distinct from analytical
success. Duplicate equivalent completed assessments reuse the existing job without another
provider call; scope is the same CV run/digest, subject, options and provider configuration.
No global exactly-once or billing guarantee is claimed.

Private evidence, every native acceptance artifact and reports were denied to another
rental and to unauthenticated requests. Original bytes/hashes survived processing; reads
after reopening storage returned the same validated report. Provider opt-ins, fixed Google
host, TLS, no proxy/redirect inheritance, byte/time/retry limits, local strict schemas,
`physical_identity_verified=false`, mandatory human review and `payment_action=none`
remain intact. No production security certification is implied.

**AI subsystem integration completed**: all final gates above passed.
**NeighborLend application integration pending**: the exact existing API/worker sequence,
identity adapter requirements, consent, scoped human review and remaining application
work are in `phase-5-integration-contract.md`. No automatic dispatcher, new consolidated
HTTP schema, financial workflow or changed parent-inspection state is implied.

## Remaining limitations and external dependencies

Independent real-world accuracy validation is **BLOCKED: no permitted independently
labeled verified before/after dataset**. No accuracy/precision/recall/damage success is
claimed. Live Google API/model/account acceptance remains unverified; separate explicit
authorization is required. There are no outstanding reproducible critical software
failures in the executed tests. Synthetic masks/changes do not establish real-object
robustness, complete surface coverage, physical identity, causation or liability.

Application identity integration, frontend review/box-selection flows, secure dispatch,
deployment ACLs/retention/monitoring, representative independent evaluation and human
dispute operations remain separate handoff work. See `phase-5-handoff.md`. Stop after Phase 5.
