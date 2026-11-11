# Phase 2 integration report

Phase 2 is connected to the standalone EP application inside `ep/`. It does not import
the production backend or touch its database, upload directory, frontend or root CI.
The original Phase 1 evidence/inspection routes and completion guard remain in place.
Historical Phase 1 reports describe their original baseline, not the expanded CV suite.

## New API

All routes use the existing Bearer authorization adapter and rental membership checks.
The local fixture adapter is not production NeighborLend authentication.

| Method and route | Behavior |
| --- | --- |
| POST `/v1/inspections/{inspection_id}/cv-runs` | 202; validate authorization/evidence, enqueue only |
| GET `/v1/cv-runs/{run_id}` | Run state and versioned request configuration |
| POST `/v1/cv-runs/{run_id}/cancel` | Requesting subject only; terminal runs reject repeat transitions |
| GET `/v1/cv-runs/{run_id}/result` | Validated CV package; 409 until completed |
| GET `/v1/cv-runs/{run_id}/artifacts/{artifact_id}` | Authorized PNG attachment; matching run membership required |

Request example (replace UUIDs with authorized inspection evidence):

```json
{
  "targets": {
    "00000000-0000-4000-8000-000000000001": {"x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.9},
    "00000000-0000-4000-8000-000000000002": {"x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.9}
  },
  "config": {"device": "cuda", "max_side": 768, "timeout_seconds": 180}
}
```

Coordinates refer to the orientation-corrected full source, not screen coordinates.
Missing target boxes are permitted but those views abstain. Unknown target UUIDs, extra
request fields, NaN values and out-of-range limits are rejected. With default limits,
eight images and sixteen candidate pairs are allowed; hard maxima are twelve and thirty-six.
Participants in the rental can read results; only the creating subject can execute/cancel.
All responses inherit request IDs, `no-store`, and `nosniff`; artifact bytes have no public URL.

## Local native execution

From `NeighborLend/ep/`, use the already approved environment. Do not install this project
into the working ML environment or change packages to silence warnings.

```powershell
$epPython = 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe'
$env:PYTHONDONTWRITEBYTECODE = '1'
# Set EP_DATA_DIR and EP_LOCAL_GRANTS_FILE explicitly for your private local deployment.
& $epPython -B -m uvicorn ep_engine.main:create_app --factory --host 127.0.0.1 --port 8010
```

After creating a CV run through the API, use another native PowerShell terminal with the
same EP configuration. Set `EP_WORKER_TOKEN` to the requesting subject's existing local
Bearer token in that terminal's environment; never put it in a command argument or report.

```powershell
$epPython = 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe'
& $epPython -B scripts/run_cv_worker.py '<queued-run-uuid>'
```

No model downloads occur during startup or request processing. Approved assets must be
present with a valid receipt. `/ready` retains Phase 1 readiness semantics; it does not
promise model availability or GPU capacity. A run can be queued while a later worker
execution fails safely for missing models or insufficient resources.

## Compatibility and recovery

The only Phase 1 application edits are app lifespan/router wiring and the explicit
six-stage orchestrator path. Phase 1 repository schemas and inspection transitions are
unchanged. CV persistence uses its own database and artifact directory. ML modules import
only on worker execution, so creating the application does not load Torch or models.
The `cv` optional dependency declaration documents already present packages; no installation
was performed. The global test fixture confines worker locks/model caches to isolated test
directories while retaining all original test cases.

Run state `completed` is separate from parent inspection state `created`; Phase 3 must
introduce reviewed completion semantics for later verification/fusion/report stages.
Recovery fails interrupted work, validates persisted artifacts and removes partial outputs.
A native worker lock prevents concurrent GPU jobs and startup recovery racing live work.
Start/restart only one local service with the selected data directory; startup while a
worker holds the lock fails safely and can be retried. There is no automatic queue consumer.

## Phase 3 input contract and prerequisites

Consume validated `CVPackage` schema 2.0, source UUID/hash manifests, quality/segmentation
records, supported and rejected pairs, coordinate maps, candidates, artifact UUIDs,
model/version hashes, experimental thresholds, timings and limitations. Reauthorize
source/artifact access when constructing any later input. Never pass arbitrary local
paths or assume a candidate is damage; inconclusive and partial results must remain valid.

Before any later integration, obtain independently reviewed physical-object datasets,
evaluate viewpoint/identity/segmentation/change behavior across the benchmark strata,
calibrate thresholds on a separate calibration split, and review adversarial false positives.
Define remote-processing consent, authorization/retention policies and reviewed human
decision workflows before any provider receives evidence. No provider call is implemented
or authorized by this report. See the testing and benchmark reports for executed evidence
and blocked accuracy validation. Work stops at Phase 2.
