# Phase 1 implementation report

The isolated Phase 1 evidence foundation is implemented and verified by the available
local automated checks. This is a development foundation, not a production deployment
or a condition-analysis accuracy claim. Work stops after Phase 1.

Repository analysis: FastAPI/SQLAlchemy backend, React/Vite frontend, existing JWT
authentication, rental acceptance/handover/return workflows, public image storage and
YOLO category inference. The existing Gemini comparison CLI is an experiment, not an
integrated inspection system. Actual paths/functions/routes and future interaction
points are in [repository-integration-audit.md](repository-integration-audit.md).
Existing backend code was inspected read-only and never imported/executed for EP tests.

Environment: user-approved `neighbourlend_yolo`, Python 3.11.16. The originally specified
`neighborklend-yolo` was absent. CUDA runtime 12.8 is available on an 8 GB RTX 4060 Laptop
GPU. Exact package versions and the approved pytest-cov/coverage installation are in
[environment-audit.md](environment-audit.md). No existing ML/application dependency
was changed, no separate environment was created, and no model weights were downloaded.

The complete source/deliverable inventory is [file-tree.txt](file-tree.txt).
Generated test/runtime files are separately kept under ignored directories inside EP.

| Component | Responsibility |
| --- | --- |
| `ep_engine/config.py` | Bounded EP-only settings, local path confinement, explicit CORS origins |
| `ep_engine/main.py` | FastAPI factory/lifespan, bounded ASGI request handling, typed endpoints, correlation/error boundary, dependency injection |
| `ep_engine/core/` | Public domain errors and fail-closed/local-fixture authorization integration |
| `ep_engine/schemas/` | Versioned evidence/inspection/finding/localization/API contracts |
| `ep_engine/services/images.py` | Actual JPEG/PNG decoding, limits, hashing and separate normalized derivative |
| `ep_engine/services/evidence.py` | Authorized ingestion, scoped deduplication, transactional file/metadata cleanup and integrity-checked reads |
| `ep_engine/services/inspections.py` | Rental/stage/integrity checks and truthful record creation/retrieval |
| `ep_engine/storage/` | Private opaque local files, SQLite schema/transactions, state machine and startup recovery |
| `ep_engine/pipeline/` | Nine replaceable stage protocols and ordered evidence-citation/error/abstention contracts; no inference implementation |
| `tests/` | Isolated unit/integration/security/regression tests and deterministic decoder samples |
| `scripts/` | Local verification runner, fixture generator, read-only syntax audit, boundary/inventory checker and actual-results reporter |
| `docs/` | Audits, contracts, architecture/security/benchmark specifications, reports and machine-readable verification evidence |

Implemented behavior: authenticated stage-specific JPEG/PNG ingestion; original
preservation and SHA verification; orientation-corrected metadata-stripped PNG derivatives;
opaque private storage; same-rental participant reads; scoped duplicates; SQLite
persistence/foreign-key links/schema versioning; state-transition rejection; rollback
and startup recovery; typed versioned APIs; sanitized dependency/runtime errors;
unavailable inference state; evidence-cited future stage/finding contracts.

Verified APIs are `/health`, `/ready`, `/v1/evidence`, `/v1/evidence/{id}`,
`/v1/evidence/{id}/content`, `/v1/inspections`, `/v1/inspections/{id}` and OpenAPI.
Examples and response/error/authentication details are in [api-contract.md](api-contract.md).
Verification used FastAPI TestClient/HTTPX, real Pillow decoding, real isolated SQLite and
filesystem operations; a public network deployment was not performed.

All final test counts, actual coverage, exact executed commands, prior failures/fixes,
warning, isolated artifact locations and remaining verification gaps are in the mandatory
[testing-report.md](testing-report.md). Coverage includes branch measurements and exceeds
the requested 85% gate. It does not prove correctness or complete security. Static
analysis uses Ruff's correctness/import/bugbear/security rules plus format checking.

Security: access fails closed unless an adapter is explicitly configured. No client ID,
role or filename is trusted. Authorized rental membership governs metadata/content and
inspection reads. Private bytes have no static mount or returned filesystem path.
Metadata/original/derivative integrity is verified at defined boundaries. Tests cover
positive and negative access/integrity/input flows. See [security-model.md](security-model.md)
for inherited Windows ACL limits and the remote-client versus trusted-host threat boundary.

Deferred: production identity adapter, real rental-state integration, remote private
storage, durable analysis worker, quality/segmentation/embeddings/alignment/change/LLM
implementations, calibrated evaluation, report persistence/completion, production
deployment, retention/deletion, quotas/load testing, frontend/payment/dispute changes.
The service does not infer damage or financial responsibility. Every transition to
completed is rejected in Phase 1; new inspection records truthfully remain unavailable.

Phase 2 prerequisites: independently annotated real image sets with consent and hashed
manifests; object-level split isolation; documented stage artifact formats/preprocessing;
license/version/ABI and resource review before weight downloads; tests for device choice,
OOM/timeout/cancellation, low-quality/unmatched evidence and explicit abstention.
Prefer worker-lifetime lazy model loading, eval/inference mode and bounded serialized
GPU work. The observed 8 GB GPU capacity is not evidence that multiple large models fit.
Use [benchmark-specification.md](benchmark-specification.md) for the twelve required strata,
ground-truth methodology, metrics and leakage controls. No AI ground truth or performance
metric was fabricated. Later phase work remains unimplemented.

Change boundary: initial Git status was clean. [change-boundary.json](change-boundary.json)
records the final changed paths and any paths outside EP. All repository additions and
modifications are inside `NeighborLend/ep/`; no existing backend/frontend/root files, CI,
Docker Compose, environment files, migrations, models or weights were modified. No
commit was created. The only expressly authorized external write was the two Conda
testing-package additions; pip temporary files were redirected inside EP.
