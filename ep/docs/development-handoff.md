# Phase 3/4 handoff

Gemini compatibility extension: see [provider guide](gemini-provider.md). The existing
assessment layer now supports official Google REST via `EP_VLM_PROVIDER=gemini` and
environment-only `GEMINI_API_KEY`, with both external-processing opt-ins still required.
No live request is authorized by this extension; synthetic images and mocked HTTP only.
Phases 1–4 remain implemented; do not rebuild them or access the excluded image collection.
Extension verification: 82 targeted tests passed; complete `all --synthetic-only` run
203 passed, 2 documented photo skips, 0 failures/errors. Controlled pretrained CPU/CUDA,
Ruff lint and formatting passed. Live Google API acceptance remains unverified.

Milestone implementation and controlled verification finished, 2026-11-08. Stop after Phase 4.
Strict synthetic-only verification: never read `test_images/`
or `.test-artifacts/real-image-evaluation/`; preserve historical evaluation reports.

Existing `cv/pipeline.py` already connects six CV stages, including SIFT/RANSAC,
mask-aware homography/overlap and SSIM candidates. Keep similarity/quality thresholds.
Extend these contracts conservatively; do not build a parallel alignment engine.

Implemented `assessment/{contracts,engine,providers,store,service,api}.py` and
`scripts/run_assessment_worker.py`. Assessment schema 4.0 reuses existing last-three stage
protocols via `Orchestrator.run_assessment`; CV schema 2.0 remains compatible. Gated,
bounded crop/context requests include source boxes, frame IDs and hashes. Default provider
is unavailable; explicit offline mocks are labeled. Optional HTTPS JSON gateway requires
operator and request opt-in, credentials, timeouts/retry/byte limits. No live call occurred.
Results live in a separate SQLite database, preserve source citations and always require
human review. Duplicate jobs reuse CV/config-bound results. Parent Phase 1 status is unchanged.

Test-source scan: existing tests do not reference excluded photographs/artifacts. Two
`test_cv_real.py` cases load a separate bundled photograph; synthetic-only collection
explicitly skips them. Parent pytest audit hook refuses excluded paths. New controlled
native tests use generated pixels, never photographs. Use
`scripts/verify.py <category> --synthetic-only`. All artifacts stay in EP.

Verified: baseline 112 passed/2 documented photo skips; final complete controlled suite
158 passed, 0 failed/errors, 2 documented bundled-photo skips; 92.85% combined coverage
against the unchanged 85% gate. Native pretrained CUDA synthetic-change path reaches the
explicit mock VLM; CPU unchanged path avoids the provider. Lint and formatting pass.
One rerun safely refused two native tests at the host-memory reserve. After RAM recovered,
the final complete run passed without changing the guard. Logs: `.test-artifacts/phase34-*.log`.

Main contract/operator guide: `docs/phase-3-4-implementation.md`; exact changes, results and
commands: `docs/phase-3-4-report.md`. No implementation work remains in this milestone.
Resume by reading these files, then run `scripts/verify.py all --synthetic-only` with the
approved Conda interpreter; inspect only a failing component if changes are needed.
Later: separate newly verified image dataset and an explicitly permitted real
VLM endpoint/consent review; do not revive exploratory images or imply production accuracy.
