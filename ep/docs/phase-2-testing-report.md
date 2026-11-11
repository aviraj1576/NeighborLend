# Phase 2 testing report

Date: 2026-11-08, Asia/Calcutta. Status: implementation and software verification passed;
independent real-world accuracy validation is blocked by absent reviewed labels.
No claim of universal reliability, calibrated confidence or physical-damage accuracy is made.

## Executed checks

All tests ran natively using
`D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe` (Python 3.11.16). The original
pre-implementation baseline was rerun: 60 passed, 99.08% coverage, lint/format passed.
See `phase-2-baseline-report.md`; its results were not assumed from historical Phase 1.

Final coverage execution: **114 passed, 0 failed, 0 errors, 0 skipped** in 55.55 seconds.
All 60 original cases still pass; 54 cases were added. Original test-case files are
unchanged. The shared fixture was extended to isolate new worker locks and model caches.

| Category | Passed | Principal behaviors |
| --- | ---: | --- |
| Unit | 40 | Quality, geometry, differences, contracts, coordinates, metrics, worker timeout/cancel/failure and actual low-quality native subprocess |
| Integration | 33 | Phase 1 API/persistence, connected CV stages, partial/missing views, private artifacts, worker state/recovery/rollback, real CUDA and CPU pipelines |
| Security | 29 | Rental authorization, malformed images, model allowlists/hashes/checkpoints, resource bounds, forged outputs/citations and private artifacts |
| Regression | 12 | Original ingestion/storage/identifier/state/orchestrator defects; additional Phase 2 regression scenarios live with their integration/security tests |
| Total | 114 | Two genuine pretrained tests included, with no skips |

Additional executed checks: both native pretrained probes; five final authenticated
API-to-native-worker benchmark cases; generated manifest/hash/split validation and
label-aware evaluation; Ruff lint and formatting; final asset,
environment-version and repository-boundary audit. All these checks passed. Benchmark
accuracy fields explicitly report blocked, not success metrics.

## Exact commands

Use native PowerShell from `NeighborLend/ep/`:

```powershell
$epPython = 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe'
& $epPython -B scripts/verify.py unit
& $epPython -B scripts/verify.py integration
& $epPython -B scripts/verify.py security
& $epPython -B scripts/verify.py regression
$env:EP_RUN_REAL_CV = '1'
& $epPython -B scripts/verify.py all
& $epPython -B scripts/verify.py coverage
& $epPython -B scripts/verify.py real
& $epPython -B scripts/verify.py lint
& $epPython -B scripts/verify.py format
& $epPython -B scripts/probe_phase2_models.py
& $epPython -B scripts/benchmark_phase2.py
& $epPython -B scripts/evaluate_phase2.py .test-artifacts/phase2-benchmark/manifest.json --predictions .test-artifacts/phase2-benchmark/predictions.json --output .test-artifacts/phase2-benchmark/evaluation.json
& $epPython -B scripts/verify_phase2_boundary.py
```

The category commands are available separately. The final `coverage` command executed
every category together with the real-inference flag; `real` was also executed separately.
The baseline `all`, `coverage`, `lint`, and `format` commands ran before implementation.
Without the real flag, exactly two hardware tests skip with explicit reasons. Do not
interpret an offline-only run as proof of real pretrained behavior.

## Actual coverage and scope

Combined statement/branch coverage: **93.34435717238529%** (93.34%), gate **85% unchanged**.
Statements: 1,809/1,897 (95.36%). Branches: 449/522 (86.02%). Missing statements: 88;
missing branches: 73, with 69 partial branches. This includes every implemented module
under `ep_engine`, including model loading, API, worker, storage, evaluator and geometry.
It does not include scripts, tests or third-party downloaded source outside that package.
There are no new application-code coverage exclusions. The 41 default-excluded lines
belong to existing abstract Protocol declarations, not executable CV/security operations.
Ruff excludes `.runtime` and `.test-artifacts` to avoid formatting vendor/generated files.

Selected combined module coverage: model adapter 98%, contracts 96%, worker lock 93%,
allowlisted assets 92%, subprocess worker 91%, artifact writer 90%, CV store 89%,
service 82%, geometry and pipeline 84% each. The aggregate passes, but remaining branch
gaps are real; coverage is not proof of correctness. Examples include rarer alternate-pair
rejections, unusual filesystem failures and forcibly killing an unresponsive child after
the termination grace period. These remain limits of verification, not silent guarantees.

Machine evidence: `.test-artifacts/coverage.xml` (JUnit), `coverage.json`,
`coverage-html/index.html`, `real.xml`, runner execution JSONs and
`docs/phase-2-verification.json`. Subprocess benchmark execution is verified separately;
its child coverage is not artificially added to pytest's coverage totals.

## Positive, negative and failure scenarios

Tests exercise genuine pretrained masks/embeddings and complete connected stages on CUDA
and CPU. Test-only injected adapters isolate deterministic matching/candidate scenarios;
their results are never counted as model-performance evidence. A real native subprocess
also executes low-quality gating without loading a model. The full five-case benchmark
uses the actual API, private storage and real pretrained subprocess execution.

Negative paths include missing/wrong assets, changed manifest, unapproved URLs, redirected
or oversized transfer, Git/SHA mismatch, missing receipt, unsafe checkpoint values/keys,
NaN/incorrect model shapes, CPU selection without CUDA, unavailable CUDA, host/GPU memory
reserve, injected OOM, invalid boxes, extreme crop ratio, empty/full/invalid masks,
low resolution/blur/exposure, insufficient keypoints/overlap, unstable transformations,
forged citations/results, unauthorized/cross-rental reads, cancellation, deadline expiry,
worker failure, directory creation failure, queue/concurrency limits, restart interruption,
artifact corruption, malformed PNG metadata and transaction commit failure.

Critical operations have acceptance and rejection checks: model transfer/receipt,
safe checkpoint loading, rental access, source hashes, artifact storage/retrieval,
worker bounds, recovery and output validation. No test intentionally exhausts actual GPU
or host memory; deterministic failure injection covers those unsafe conditions.

## Defects found and fixes verified

| Scenario | Fix and verification |
| --- | --- |
| Failure after artifact directory promotion but before DB commit | Broadened rollback cleanup to cover transaction commit; injected SQLite commit failure leaves no promoted result |
| Work-directory creation exception after claim | Moved creation into failure/cleanup handling; run becomes failed instead of remaining processing |
| Hash-valid artifact with false dimensions or non-PNG contents | Commit/read validation now checks actual PNG format and dimensions; forged artifact tests reject it |
| Candidate/outcome/citation claims inconsistent with worker evidence | Package validation requires source dimensions/digests, complete stage coverage, cited masks and comparable candidate pairs; forged contracts rejected |
| Recovery or another worker racing active processing | Native Windows byte lock wraps execution/recovery across data directories; active-lock regression rejects both and permits work after release |
| Extreme thin object crop could inflate intermediate resize | Aspect-ratio guard rejects it before allocation; regression verifies typed refusal |
| Wrong-size local model file could be read before validation | File size is now checked before allocation; negative test forbids reading its contents |
| Finite embedding values could overflow their norm | Nonfinite norms are rejected before normalization; extreme finite-value regression added |

Earlier offline runs had two explicitly skipped real tests and 82.27% coverage, correctly
failing the gate. Real inference and meaningful security/failure tests raised measured
coverage; the threshold was never lowered. Intermediate Ruff errors were fixed and the
final lint/format gates passed.

Two early end-to-end attempts stopped under actual low host RAM with `memory_reserve`.
This was the intended safety behavior, not a forced OOM or a successful comparison.
After the user freed memory, final real comparisons all succeeded. No program was closed,
memory setting changed or guard weakened to force execution.

Seven retained warnings: one upstream Starlette/HTTPX TestClient deprecation and six
upstream disabled/unavailable-xformers notices. No dependency was changed to hide them.

## Isolation, unresolved limits and next-phase prerequisites

Pytest data, isolated SQLite databases, caches, worker locks, temporary files and reports
are confined to `ep/.test-artifacts/`. Existing model assets are read-only test inputs.
Benchmark storage is separately isolated under `.test-artifacts/phase2-benchmark/private`.
No test loads the production backend database or production evidence. The final audit
reports zero changes outside EP and zero audited package-version changes. No root CI
configuration was edited; no commit was created.

There are no reproducible unresolved critical software test failures. Empirical identity,
viewpoint, segmentation, candidate localization and physical-damage accuracy are **blocked**:
the only photographed smoke source has synthetic derivatives and no reviewed truth.
Independent camera-angle captures, real damage, same-category different objects,
occlusion, pre-existing defects and multi-object real datasets remain unvalidated.

Local authorization is a fixture, thresholds are experimental, and the explicit worker
has no production scheduler/distributed retry guarantee. Reviewed native Windows ACLs,
real NeighborLend authorization, retention/operations policies and real data evaluation
are required before deployment. Phase 3 also needs reviewed annotations, locked object-level
splits, calibrated thresholds and tests for provider input citations, abstention and
completion semantics. No later-phase provider/payment implementation was added.
