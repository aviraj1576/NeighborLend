# Phase 2 pre-implementation baseline

Date: 2026-11-08, Asia/Calcutta. The actual repository root and root AGENTS.md were
verified/read. Existing Git status is **not clean**: the complete Phase 1 `ep/` directory
is untracked (`?? ep/`). This existing user/session work is preserved; no reset, checkout,
staging, commit, migration, root configuration change or backend import was performed.

Before adding audit helpers, hashes of all **58 existing EP source/deliverable files**
and the full Git status were recorded under `.test-artifacts/phase-2-baseline/`.
No Phase 1 application, schema, API, test, runner or existing documentation file has
been edited during the pre-installation audit. Audit-only additions are listed below.

Required baseline commands executed from `ep/` with the approved interpreter:

```powershell
$epPython = 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe'
& $epPython -B scripts/verify.py all
& $epPython -B scripts/verify.py coverage
& $epPython -B scripts/verify.py lint
& $epPython -B scripts/verify.py format
```

| Check | Actual result |
| --- | --- |
| All original Phase 1 tests | 60 passed, 0 failed, 0 skipped |
| Coverage suite | 60 passed, 0 failed, 0 skipped |
| Combined statement/branch coverage | 99.08%, gate 85% unchanged |
| Statements / branches | 630/633 statements; 126/130 branches |
| Ruff lint | Passed |
| Ruff format | Passed; 49 Python files at this baseline, including the new environment-audit helper |

The environment audit helper was formatted before baseline checks; no application code
changed. Original 60 tests remain intact. The upstream Starlette/HTTPX TestClient
deprecation warning remains; it is not a test failure and no package was changed to hide it.

Baseline commands/exit records, stdout logs, JUnit results, coverage JSON, initial Git
status and original source hashes are retained under `.test-artifacts/phase-2-baseline/`.
The baseline runner continues to use isolated per-test SQLite/private directories under
EP; no production storage, existing database or network inference is used by these tests.

Additional read-only audit: actual TorchVision NMS ran on CPU and CUDA; OpenCV image
conversion and SIFT/ORB availability were checked. This is **not pretrained inference**.
No compatible model weights were found in EP or the inspected default Torch/Hugging Face
caches. The only repository model found is the existing backend YOLO category checkpoint,
which was left untouched. The Hugging Face cache contains BERT/MiniLM entries, not the
selected models. Other arbitrary system directories were not exhaustively searched.

The only EP images found are the two 24x16 synthetic decoder fixtures. No real labeled
before/after benchmark or consent/provenance manifest is available in EP. Therefore
empirical comparison accuracy and the required real-image demonstrations are not yet
verified. No substitute ground-truth labels or AI metrics were generated.

Audit-only additions at this gate:

- `scripts/audit_phase2_environment.py`: package/device/operator/RAM audit, EP-confined caches.
- `scripts/audit_phase2_weight_headers.py`: HTTPS HEAD availability/size checks; no model bodies.
- `docs/phase-2-baseline-report.md`: this verified baseline.
- `docs/phase-2-model-audit.md`: model/dependency/license/resource review.
- `docs/phase-2-installation-plan.json`: precise official download allowlist and targets.
- `docs/phase-2-implementation-plan.md`: gated continuation, risks and verification plan.
- `docs/phase-2-audit-boundary.json`: final original-file hash and Git-boundary verification.

Status: **Phase 2 is not implemented or complete.** Model download authorization is
the next mandatory gate in the user's brief. No weights, packages or pretrained source
modules have been installed/downloaded during this audit; reviewed remote code was
retrieved as text through read-only documentation/repository tools only.
