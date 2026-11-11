# API contract v1

Service base: local `http://127.0.0.1:8010`. OpenAPI: `/openapi.json`; interactive docs:
`/docs`. Contract schemas use `schema_version: "1.0"`. All responses carry a generated
`X-Request-ID`, `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.

| Endpoint | Success | Behavior |
| --- | --- | --- |
| `GET /health` | 200 | Liveness `{ "status": "ok" }`; no authentication |
| `GET /ready` | 200 or 503 | Requires configured authorization and working SQLite/storage; explicitly reports `pipeline: "unavailable"` |
| `POST /v1/evidence` | 201; 200 scoped duplicate | Raw binary JPEG/PNG body, query metadata; authenticated lender uploads before, borrower after |
| `GET /v1/evidence/{evidence_id}` | 200 | Authorized rental participants; metadata only, no filesystem paths/storage refs/subject IDs |
| `GET /v1/evidence/{evidence_id}/content` | 200 | Original bytes after SHA-256 check; authorized attachment download |
| `POST /v1/inspections` | 201 | Validates evidence selection/integrity and persists a `created`, `unavailable` record |
| `GET /v1/inspections/{inspection_id}` | 200 | Authorized rental participants; real persisted status |

Protected endpoints use `Authorization: Bearer <token>`. Unconfigured authorization
returns 503; absent/invalid credentials return 401 with `WWW-Authenticate: Bearer`;
wrong rental membership or capture role returns 403. Client `user_id`, `role`, filename,
and custom identity headers never grant access. Local configured tokens resolve to
server-side grants, not claims in request metadata. Production identity verification
requires a future adapter.

Evidence query: `rental_id` (1–128 ASCII alphanumeric/underscore/hyphen), `stage`
(`before`/`after`), optional `viewpoint` (at most 80 characters), optional ISO datetime
`capture_timestamp`. Dates/view labels are unverified. A declared Content-Type must
match decoded JPEG/PNG content; absent Content-Type permits content detection. Filename
and extensions are not used. Unknown query parameters are ignored by FastAPI.
Whole request bodies, including inspection JSON, share the configured byte limit.

Illustrative requests (tokens and IDs are placeholders, not recorded execution output):

```powershell
curl.exe -X POST 'http://127.0.0.1:8010/v1/evidence?rental_id=rental-1&stage=before&viewpoint=front' -H "Authorization: Bearer $env:EP_LOCAL_TOKEN" -H 'Content-Type: image/jpeg' --data-binary '@tests/fixtures/sample.jpg'
```

```json
{
  "schema_version": "1.0",
  "rental_id": "rental-1",
  "reference_ids": ["<before evidence UUID>"],
  "return_ids": ["<after evidence UUID>"]
}
```

Send inspection JSON to `/v1/inspections` with `Content-Type: application/json` and
Bearer credentials. Both lists require 1–20 distinct UUIDs; there can be no overlap.
Selections must refer to the same rental and the correct before/after stages. Unknown
JSON fields, including client-assigned status, are rejected. Missing/wrong selections
return 422; invalid/tampered bytes return 409.

Evidence response fields: opaque UUID `id`, `rental_id`, `uploader_role`, `stage`,
`viewpoint`, `capture_timestamp`, `metadata_verified:false`, verified `content_type`,
orientation-corrected `width`/`height`, original `byte_size`/`sha256`, server UTC
`uploaded_at`, `validation_status` (`validated` or recovery-marked `invalid`).

Inspection response adds UUID `id`, `status:created`, server UTC `created_at`,
`completed_at:null`, `pipeline_version:phase-1-unavailable`,
`result_status:unavailable`, `error_code:null`, and echoes the validated selection.
No findings are fabricated. There is no public queue/transition/analysis endpoint.

Consistent error envelope (illustrative):

```json
{
  "error": {"code": "invalid_request", "message": "Request validation failed"},
  "request_id": "<same UUID as X-Request-ID>"
}
```

404 denotes missing resources/routes. 409 denotes state conflict/integrity failure.
413 denotes body/byte/dimension/pixel limits. 415 denotes MIME mismatch or animated
evidence. 422 denotes malformed/empty/corrupt/unsupported images or invalid request
schemas/selections. 503 denotes unconfigured authorization, unavailable dependencies
or unimplemented pipeline transitions. Unexpected exceptions return sanitized 500.
Validation errors omit raw request values to avoid reflecting sensitive data.
OpenAPI documents Bearer security and typed JSON/error responses.
# Phase 2 API extension

The original Phase 1 routes documented here retain their behavior. New CV run, result,
cancellation and private artifact routes are specified in
[Phase 2 integration/API report](phase-2-integration-report.md). CV completion is separate
from parent inspection completion; GPU work runs only in the explicit native worker.

