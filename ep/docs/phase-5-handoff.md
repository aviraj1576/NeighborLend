# Phase 5 handoff

Final gate results and release status: `phase-5-release-report.md`. Actual endpoint and
worker handoff: `phase-5-integration-contract.md`. Read those instead of rebuilding Phases
1-4 or repeating historical audits. Stop after this release milestone.

The existing engine connects private evidence ingestion, inspection, six-stage native
pretrained CV, strict Gemini-compatible evidence preparation/assessment, conservative
fusion, private persistence and authorized retrieval. Native acceptance now traverses
both existing worker entrypoints through the API lifecycle, with generated pixels and
only the Gemini HTTP boundary mocked. Production NeighborLend backend/frontend
integration is pending. Parent Phase 1 inspection semantics remain unchanged.

## Native Windows setup and verification

Use the existing Windows Conda environment and approved pinned local models. No packages,
models, OS settings or root files were changed. No Linux environment is needed or allowed.
Do not blindly install the project or alter the environment.

From `ep/` in PowerShell:

```powershell
$epPython = 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe'
& $epPython -B scripts/verify.py all --synthetic-only
& $epPython -B scripts/verify.py coverage --synthetic-only
& $epPython -B scripts/verify.py lint
& $epPython -B scripts/verify.py format
```

The runner confines generated files to EP, enables controlled native tests, and retains
RAM/VRAM guards. Do not weaken reserves to pass tests; free unused application memory
manually if a future run safely refuses execution. Synthetic-only testing blocks excluded
paths and explicitly skips two legacy bundled-photograph cases. Never run old real-image
scripts or access `test_images/`, its derived exploratory artifacts, or historical image
evaluation inputs during this milestone. Historical reports remain untouched.

`tests/integration/test_release_native.py::test_native_api_to_private_review_report`
is the release acceptance test: CUDA uses two generated references/two edited returns;
CPU uses an unchanged generated pair. The test authenticates through local fixture grants,
invokes real worker entrypoints, runs the hidden CV subprocess, checks official Gemini
request serialization with MockTransport, validates artifacts/citations and reopens
databases for report retrieval. `.test-artifacts/phase5-release/latest-{cuda,cpu}.json`
points to each latest isolated case and measurements. Every case retains its own private
evidence/database/artifacts, CV package, key-free manifests and result summary. These are
synthetic software diagnostics, not a labeled damage dataset. Gemini adapter metadata
identifies its wire protocol; `mocked_http_only=true` and explicit mock explanations in
these test results distinguish them from genuine VLM inference.

## Gemini and future external validation

Keep `EP_VLM_PROVIDER` unset/disabled by default. `mock` is offline. A future permitted
Google run requires explicit `gemini`, an image/JSON-capable `EP_VLM_MODEL`, exported
`GEMINI_API_KEY`, operator `EP_VLM_ALLOW_EXTERNAL=1` and per-job `allow_external=true`.
Never print keys, put them in arguments or reports, or load a repository dotenv file.
Endpoint validation, TLS, bounded retries/requests and local citation validation remain
mandatory. Optional price settings are explicit estimates, never invented billing.

Before any live test: obtain specific authorization for the chosen model, permitted
evidence, external transmission and budget; verify credentials privately, privacy/retention
terms and account/model availability; then run a separately bounded test and document
actual results. No live API acceptance or VLM quality is verified by this release.

Real-world evaluation remains blocked pending newly collected, consented, independently
verified before/after photographs of the same physical objects, independent annotations,
coverage of capture/lighting/occlusion/damage confounders, fixed splits and prespecified
abstention/localization metrics. Do not revive exploratory photographs, fabricate labels,
claim accuracy from synthetic patches or tune thresholds to these release fixtures.

Deployment still needs production identity/rental authorization, Windows ACLs, retention,
secure worker dispatch, monitoring/recovery and reviewed application integration. Human
review/dispute decisions remain external. The engine cannot authorize money movement.
