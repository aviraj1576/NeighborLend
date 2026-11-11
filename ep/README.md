# NeighborLend Evidence Processing Engine — Phases 1–4

The standalone [EP v3.1 advisory inspection API](docs/ep-v31.md) adds numerical
guards, per-view failure isolation, measured half-turn correspondence fallback,
instance ambiguity checks, object-region sampling bounds, original-data review
crops and a strict versioned report. See its [measured release report](docs/ep-v31-release-report.md).
The [current refinement report](docs/ep-v31-refinement-report.md) covers object-crop
matching, scoped local surface evidence, original-pixel scans, and measured DINO batching.
It has no application integration or financial authority.

The standalone [CV/VLM comparison harness](docs/vlm-evaluation.md) benchmarks
matched CV-only, VLM-only and geometry-gated hybrid observations with free-only API
admission, private caching and independent-label metrics. See its
[measured evaluation](docs/vlm-evaluation-report.md) before considering integration.

The opt-in [EP v3 hybrid engine](docs/ep-v3.md) adds optional verified LoFTR matching,
CUDA appearance analysis, experimental GPU geometry/warping, bounded embedding
caching and resolution-aware comparison. It runs through `scripts/run_v3.py` and
has no NeighborLend application integration or financial authority. Current results
and limitations are in the [completion report](../docs/final-payment-ep-v3-report.md).

The 2026-11-10 advisory CV extension adds foreground-mask validation, full-object
rotation-pooled DINOv2 features, precise RootSIFT geometry, boundary-change hypotheses,
recapture guidance and per-image resource telemetry. Existing quality thresholds and
checkpoints remain unchanged. See [current extension and verification](docs/engine-improvements-20261110.md).
The milestone descriptions below retain their historical scope; real-image improvement
evaluation is isolated under `.test-artifacts/engine-improvement-20261110-01/`.

The current Phase 3/4 milestone uses **synthetic-only verification**. `test_images/`
and all derived exploratory outputs are excluded. Historical real-image reports remain
historical; no photograph-based calibration or accuracy evaluation is part of this milestone.
Use the approved native Windows interpreter and `scripts/verify.py <category> --synthetic-only`.
That mode blocks excluded paths and explicitly skips the two existing bundled-photo tests;
new controlled native tests generate pixels for CUDA/CPU verification.

Phase 3 reuses the existing geometric alignment and candidate stages with additional
failure safeguards. Phase 4 queues a separate, private, human-review assessment with a
disabled-by-default provider, explicit offline mock, or opt-in JSON HTTPS VLM gateway.
No live provider calls or environment package changes were made during development.

- [Phase 3/4 operator and API contract](docs/phase-3-4-implementation.md)
- [Phase 3/4 engineering report](docs/phase-3-4-report.md)
- [Development handoff](docs/development-handoff.md)

The remaining Phase 1/2 setup and benchmark commands below are historical capabilities;
photograph-loading benchmark/probe/evaluation commands are outside this milestone.

Standalone private evidence ingestion and a native Windows pretrained CV comparison
pipeline. Phase 2 connects quality checks, EfficientSAM-Ti segmentation, DINOv2-S/14
embeddings, SIFT/RANSAC alignment and local appearance-change candidates. Comparisons
may remain inconclusive. Candidates are not confirmed damage or physical identity proof.
No training, paid API calls, liability decisions, deposit deductions or dispute settlement
are implemented. Parent inspections remain `created` with analysis `unavailable`.

The package is `ep_engine` to avoid colliding with the existing backend's `app` package.
No backend modules, root `.env`, existing database, or public upload directories are used.

Use PowerShell from `NeighborLend/ep/`:

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
```

The requested name `neighborklend-yolo` was absent. The user approved the actual
`neighbourlend_yolo` environment. See [environment audit](docs/environment-audit.md)
for exact versions and the approved test dependency addition. All required application
packages already existed; do not blindly install this project into the YOLO environment.
For a future clean, separately approved environment, `python -m pip install -e '.[dev]'`
uses the declared dependencies. Model weights are not part of the installation.

Local startup (no root configuration is read):

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& $epPython -B -m uvicorn ep_engine.main:create_app --factory --host 127.0.0.1 --port 8010
```

By default protected routes and `/ready` return 503 because no authorization adapter
is configured. `/health` is liveness only. To enable local fixture authorization, create
an untracked `ep/.runtime/local-grants.json`, restrict its OS permissions, and explicitly
set `EP_LOCAL_GRANTS_FILE` to its absolute path. It is an array in this format:

```json
[
  {
    "token": "<generate-a-long-random-local-only-token>",
    "grant": {"subject": "local-lender", "rentals": {"rental-1": "lender"}}
  },
  {
    "token": "<a-different-long-random-local-only-token>",
    "grant": {"subject": "local-borrower", "rentals": {"rental-1": "borrower"}}
  }
]
```

No token is issued by EP. Do not use the illustrative strings as credentials or expose
this development service publicly. This fixture mechanism does not verify NeighborLend
users; production requires the integration adapter documented below.

Configuration is read only from exported `EP_*` variables. `EP_DATA_DIR` defaults to
`ep/.runtime` and must resolve below `ep/`. Relative paths resolve against `ep/`.
`EP_MAX_UPLOAD_BYTES` defaults to 10 MiB, `EP_MAX_PIXELS` to 16 million, and
`EP_MAX_DIMENSION` to 8192. `EP_CORS_ORIGINS` is a JSON array of explicit origins,
default `[]`. `.env.example` documents values; no dotenv file is automatically loaded.

Evidence uploads use a bounded raw JPEG/PNG request body and query metadata, avoiding
multipart spool files. Original bytes are immutable by convention and SHA-256 checked;
orientation-corrected, metadata-stripped PNG derivatives are separate. Downloads require
authorization and are attachments; no static evidence mount exists.

The local runner disables bytecode/plugin auto-loading and confines pytest, coverage,
Ruff, temporary data and reports to `ep/.test-artifacts/`. Test fixtures also isolate
native worker locks and model caches. Real tests read approved model assets without
altering them. Without `EP_RUN_REAL_CV=1`, two real-inference tests explicitly skip.
Do not run the existing backend
tests as part of EP validation. Regenerate synthetic decoder samples only with
`& $epPython -B scripts/create_test_fixtures.py`; these contain no AI labels.

Documentation:

- [Architecture](docs/architecture.md), [API contract](docs/api-contract.md)
- [Repository audit](docs/repository-integration-audit.md), [integration proposal](docs/integration-contract.md)
- [Security model](docs/security-model.md), [test plan](docs/test-plan.md)
- [Testing report](docs/testing-report.md), [Phase 1 report](docs/phase-1-report.md)
- [Future benchmark specification](docs/benchmark-specification.md)
- [Phase 2 architecture](docs/phase-2-architecture.md)
- [Phase 2 model audit](docs/phase-2-model-audit.md)
- [Phase 2 testing report](docs/phase-2-testing-report.md)
- [Phase 2 benchmark report](docs/phase-2-benchmark-report.md)
- [Phase 2 integration and API](docs/phase-2-integration-report.md)
- [Label-aware evaluation workflow](docs/phase-2-evaluation-workflow.md)

Phase 2 runs only in the approved native Windows Conda environment. All 26 approved
source/license/weight files (129,383,449 bytes) are under `.runtime/models/`; no new
packages were installed. Startup and requests never download models. The immutable
installation plan retains its historical approval-gate text; actual authorization and
verified execution are recorded in the model audit and current reports.

The new POST `/v1/inspections/{id}/cv-runs` queues a comparison with explicit normalized
target boxes per evidence UUID. A separate native worker executes it:

```powershell
# Use the same EP_DATA_DIR / EP_LOCAL_GRANTS_FILE as the API.
# Set EP_WORKER_TOKEN privately to the requesting subject's token in this terminal.
& $epPython -B scripts/run_cv_worker.py '<queued-run-uuid>'
```

GET `/v1/cv-runs/{id}/result` and its `/artifacts/{artifact_id}` route require rental
authorization. CV run completion does not complete the parent inspection. Worker execution
and recovery share a Windows lock, with bounded memory, queue, inputs and subprocess time.
This is an explicit local worker, without an automatic production scheduler.

Run `scripts/benchmark_phase2.py` for the documented local photograph/synthetic smoke set.
Optional standalone OpenRouter visual reasoning is implemented in
[the private inspection wrapper](docs/openrouter-v31.md); see its
[latest live-hybrid acceptance](docs/openrouter-v31-hybrid-acceptance.md) and
[native finalization](docs/openrouter-v31-finalization.md).
The existing CV API stays local. Application integration remains unvalidated.

Independent physical-object accuracy validation remains blocked pending real reviewed
labels. Phase 3 provider verification, fusion, reviewed decisions and operations remain
future work; this implementation stops after Phase 2.
