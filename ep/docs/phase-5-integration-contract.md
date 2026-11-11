# Phase 5 application integration contract

Native Windows EP subsystem integration is separate from NeighborLend application
integration. No existing backend/frontend, root configuration or application database was
changed. The following routes and fields already exist; this milestone introduces no
parallel pipeline, merged report schema or new payment authority.

## Identity and consent

Every protected request carries `Authorization: Bearer <credential>`. An `Authorization`
adapter authenticates a stable subject and current rental-to-role grants. Lenders alone
may upload `before`; borrowers alone may upload `after`. Both participants may read their
authorized rental. Another rental receives 403; missing/invalid credentials receive 401.
Only the requesting subject may execute or cancel a job. EP does not issue tokens.

Current `LocalAuthorization` and `EP_LOCAL_GRANTS_FILE` are local fixtures, not production
NeighborLend identity validation. Production requires an approved application adapter
that verifies credentials and current rental ownership; never trust a client-supplied
role or rental ID. Do not forward backend JWTs assuming EP already understands them.

Default assessment provider is disabled. `mock` is an explicitly labeled offline fixture.
Gemini requires `EP_VLM_PROVIDER=gemini`, an explicit `EP_VLM_MODEL`, environment-only
`GEMINI_API_KEY`, and `EP_VLM_ALLOW_EXTERNAL=1`. Each assessment also needs
`allow_external=true` before evidence preparation/transmission. Phase 5 authorizes no
live request; the release test replaces only the Google HTTP boundary. No browser should
receive a provider key or worker token. See the existing `gemini-provider.md` for wire limits.

## Implemented sequence

All paths are relative to the EP API, not the existing NeighborLend `/api` routes.

| Step | Actual request/result |
| --- | --- |
| Upload references | `POST /v1/evidence?rental_id=...&stage=before&viewpoint=...` with raw JPEG/PNG body and matching `Content-Type`, using lender credentials. Repeat for each selected reference. |
| Upload returns | Same endpoint, `stage=after`, borrower credentials. Optional `capture_timestamp` and `viewpoint` are unverified metadata, never inferred roles/truth. |
| Preserve provenance | Response `Evidence` schema 1.0 contains `id`, `rental_id`, `stage`, `uploader_role`, `sha256`, dimensions and validation status. 201 means new; 200 is a same-rental/stage/uploader/content duplicate. Originals and normalized derivatives remain private. |
| Create inspection | `POST /v1/inspections` with `rental_id`, `reference_ids`, `return_ids`. Schema 1.0; unique correctly staged IDs from the same rental are required. Returns 201 and inspection `id`. |
| Submit CV | `POST /v1/inspections/{inspection_id}/cv-runs`, body `{"targets":{"<evidence-uuid>":{"x1":0.16,"y1":0.16,"x2":0.84,"y2":0.84}},"config":{"device":"cuda","max_side":768}}`. Include explicit boxes for all intended sources; sample coordinates are illustrative. Returns 202 `RunRecord`, schema 2.0. |
| Poll CV | `GET /v1/cv-runs/{run_id}`. Status is `queued`, `processing`, `completed`, `failed` or `cancelled`; inspect `error_code`. Cancellation: `POST /v1/cv-runs/{run_id}/cancel`. |
| Retrieve CV | `GET /v1/cv-runs/{run_id}/result`. Schema 2.0 `CVPackage`: source IDs/hashes/dimensions, quality, segmentation, pairs, homographies, overlap, candidates, model provenance, thresholds, artifacts and limitations. 409 until a completed valid result exists. |
| Submit assessment | `POST /v1/cv-runs/{run_id}/assessments`, body `{"allow_external":false,"max_candidates":4,"max_pairs":4,"image_side":512}`. Returns 202 `AssessmentJob` with `id`, rental/inspection/CV references, digest and options. No inference runs in the handler. |
| Poll assessment | `GET /v1/assessments/{assessment_id}`. Same five job states. Requester cancellation: `POST /v1/assessments/{assessment_id}/cancel`. |
| Retrieve review report | `GET /v1/assessments/{assessment_id}/result`. Schema 4.0 `AssessmentReport`: findings across selected supported views, source hashes, CV digest, selected/unassessed candidates, provider/model provenance, uncertainty, limitations, stage statuses and usage. |
| Retrieve diagnostics | `GET /v1/cv-runs/{run_id}/artifacts/{artifact_id}` returns authorized PNG attachments. `GET /v1/evidence/{evidence_id}` returns metadata; `/content` returns the original attachment. No static evidence mount or public artifact URL exists. |

EP runs quality -> EfficientSAM-Ti -> DINOv2-S/14 -> SIFT/RANSAC -> mask-aware alignment
and overlap -> SSIM candidates -> gated cited crops/context -> provider validation ->
fusion -> persisted report. Internal `StageResult` envelopes are schema 1.0, CV packages
2.0 and assessment reports 4.0. Raw masks/features are checked for shape/type/numerical
validity before use; returned CV packages and reports are validated before persistence.

Boxes are normalized coordinates in each orientation-corrected source frame. Display a
box on that same frame, not blindly on a rotated original. Source and processing
dimensions differ when bounded downsampling applies. `Pair.homography` operates in
processing pixel coordinates, mapping reference to return; candidate before/after boxes
cite their respective frames. Provider crops preserve frame IDs, boxes, dimensions and
both prepared-image and source-artifact hashes. Never draw an overlay on an unrelated
source or assume a full-image mask has crop coordinates.

## Worker responsibilities and persistence

Use the approved interpreter from `ep/`, with API/worker `EP_DATA_DIR` and authorization
configuration pointing at the same private isolated store. A trusted native dispatcher
must explicitly start the existing workers for the requesting subject:

```powershell
$epPython = 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe'
# EP_WORKER_TOKEN is supplied privately in the process environment.
& $epPython -B scripts/run_cv_worker.py '<queued-cv-run-uuid>'
& $epPython -B scripts/run_assessment_worker.py '<queued-assessment-uuid>'
```

CV uses a hidden native subprocess with timeout/cancellation and real pinned local
models. Assessment uses the existing worker service and bounded HTTP requests. The
native lock excludes concurrent CV/assessment execution/recovery. Do not start API
startup recovery during active worker execution; worker-busy failures require bounded
retry by the dispatcher. A four-job queue bounds pending work per store. Startup marks
interrupted processing jobs failed, verifies CV artifacts and removes only orphan work
inside its configured store. Atomic SQLite commits and artifact promotion protect results.

Reuse the persisted CV run; posting CV again creates a new run. The application must
retain job IDs and avoid blind submission retries. Equivalent assessment submissions
for the same subject, CV run/digest, options and provider configuration reuse queued,
processing or completed jobs. Executing a terminal job returns invalid-transition before
any provider call. Failed/cancelled assessment retries are new jobs and may repeat an
external attempt; there is no distributed exactly-once/billing guarantee. No automatic
scheduler, job-list discovery endpoint or retention daemon is supplied.

Private originals/PNGs, `ep.sqlite3`, `cv/cv.sqlite3`, `cv/artifacts/` and
`assessments/assessments.sqlite3` stay beneath `EP_DATA_DIR`, itself confined to `ep/`.
Reads recheck source hashes, approved CV configuration and artifact integrity. Source or
CV mutation invalidates dependent assessments. Deployers must supply Windows ACLs,
encrypted backups, retention, audit operations and recovery policy before production use.

## Review and error handling

The existing assessment report is the consolidated finding list. To present one complete
inspection review, join it with its `AssessmentJob` (rental/inspection IDs), referenced
`CVPackage` (candidates, boxes, quality, unsupported views and artifact citations), and
`Inspection` (before/after membership). Check `cv_digest` and source hashes; EP rechecks
them on report reads. No new merged endpoint is implied. Never present the assessment
without the CV scope, unassessed candidates and limitations.

Job `completed` means a validated sub-result was stored. Inspect analytical statuses:

| Meaning | Implemented representation |
| --- | --- |
| Appearance difference | CV `local_appearance_change` candidate; not confirmed physical damage. |
| Possible condition change | Cited provider `possible_visible_damage`, typically report `human_review_required`; no causation or liability inference. |
| Insufficient/conflicting evidence | `inconclusive`, `insufficient_evidence`, errors/limitations; overlapping conflicts retain all observations and force inconclusive. |
| Partial scope | `partial`, unassessed candidate IDs, unmatched views and limitations; never imply unobserved surfaces are unchanged. |
| No candidate in evaluated regions | `no_visible_change` with zero candidates; a scoped CV outcome, not proof of no damage. |

Overlapping shared-frame observations are not independent confirmations. Cross-capture
physical-region deduplication is not established, so EP does not count observations as
independent votes or report calibrated probabilities. Unsupported viewpoints are not
forced to match; segmentation/matching/alignment rejection prevents provider calls for
those regions. Bad citations, truncation/refusals or provider failure create inconclusive
reports without accepted findings. Such a report may be stored by a completed assessment
job; it must never be displayed as successful damage verification. A failed/cancelled job
has no retrievable successful result. HTTP errors use sanitized error codes/request IDs;
handle 409 integrity/unavailable/transition, 413/422 invalid limits/input, 429 queue limits,
and 503 unconfigured/busy/dependency conditions without treating them as negative evidence.

The Phase 1 parent remains `created` with result unavailable; do not poll its status for
CV/assessment completion. Human review is mandatory. `physical_identity_verified=false`
and `payment_action=none` are invariant. Reviewer decisions, disputes, escrow and payment
authorization belong to separately approved application workflows.

## Remaining application work

Backend identity/grant adapter, rental-event triggers, upload/box-selection UI, trusted
worker dispatch, polling/retry UX, scoped review rendering, consent capture, human dispute
handoff and deployment operations remain pending separate approval. Native subsystem
acceptance does not claim NeighborLend application integration or production approval.
