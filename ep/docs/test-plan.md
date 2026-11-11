# Phase 1 executable specification

Tests precede each major component. All test state lives below ep/.test-artifacts,
using per-test directories and separate SQLite databases. No backend imports, external
services, root environment files, model weights, or production database connections.

| Component | Positive behavior | Failure and security cases |
| --- | --- | --- |
| Decoder | Real JPEG/PNG, original hash, EXIF orientation derivative | Empty, corrupt, disguised content, animated PNG, truncation, dimension/pixel/byte bounds |
| Storage/persistence | Private opaque keys, atomic commit, scoped deduplication, restart | Write/transaction failures, missing/tampered bytes, interrupted upload recovery |
| Authorization | Explicit local opaque token mapped to rental-specific grants | Unconfigured, absent/invalid token, forged role/user, other rental, wrong capture role |
| Inspection | Persisted before/after references, legal lifecycle | Missing/wrong/duplicate IDs, cross-rental references, invalid transition, unavailable stages, failed stage |
| API | Typed request/response, health/readiness/OpenAPI, correlation IDs | Consistent sanitized 4xx/5xx, dependency outage, excessive bodies, CORS denial |
| Regression | Stable reproduction for discovered defects | Document actual failure and fix in testing-report.md |

Coverage gate: at least 85% statement/branch combined coverage as reported by coverage.py.
Coverage does not measure reliability. Later AI benchmarks require independently
annotated real evidence; no Phase 1 model accuracy claim is permitted.
