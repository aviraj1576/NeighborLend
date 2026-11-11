# Test payment system: implementation and verification

Current release evidence, **2026-11-11**: [final payment release audit](payment-final-release-audit-20261111.md)
and [current architecture](payment-architecture.md). Fresh official Test GETs verify
three captures and both processed refunds. The backend suite passes **289 tests**
with **3 PostgreSQL skips**; frontend **40 tests**, payment lint/format and build pass.
The historical sandbox has no payment database triggers/schema-version table, its
local JWT key fails public-strength policy, and vulnerable backend dependency pins
remain. It is suitable for a supervised local demonstration of completed scenarios,
not a production release or new financial mutation demonstration. Independent
Dashboard webhook provenance and PostgreSQL behavior remain unverified.

The older dated execution results below are retained as historical evidence; they
do not mean that the genuine scenarios still await credentials or checkout.
EP v3 remains separate from application payments and AI routes.

Date: 2026-11-09 (Asia/Calcutta). This document supersedes the earlier payment
implementation handoff. The existing working tree, including untracked payment
modules, was retained and repaired. No application database was reset or migrated
during development. No Razorpay request, real payment, bank transfer or payout was
made. All balances and lender allocations are simulated accounting, not escrow custody.

## Architecture and authority

The original nine financial entities remain. `RentalEvidence` is an additional
supporting entity, not a second payment system. Financial amounts in offers and
bookings are integer paise. Existing float catalog/display columns remain for
compatibility; immutable minor-unit terms are authoritative.

1. Proposal creation snapshots participants, listing, dates, rounded daily rate,
   rental total, security deposit and complete obligation. Both chat participants
   can review these terms. Counteroffers are new snapshots. Listing changes do not
   change proposals or accepted bookings. Historical proposals without snapshots
   require a new offer; historical unfunded rentals are never considered paid.
2. Acceptance serializes on the listing, checks overlap and atomically creates the
   rental and booking. Acceptance is unavailable while payments are disabled.
3. Borrower-only checkout uses the stored booking total. A durable order operation
   precedes provider I/O. Definite HTTP validation/auth rejection permits controlled
   retry; unknown outcomes are reconciled by the existing receipt, without blind
   POST retries. Late results cannot downgrade confirmed capture.
4. Mock confirmation is authenticated, borrower-owned and state-gated. Hosted
   Razorpay test checkout requires both HMAC verification and authoritative gateway
   order/payment checks. Only captured payment posts funding and unlocks handover.
5. Handover uses private booking/stage/uploader-bound JPEG/PNG evidence. Borrower
   receipt and its condition note are persisted. Rental activation occurs after
   lender acknowledgement. The old handover aliases cannot bypass this sequence.
6. The borrower uploads return evidence. Lender approval and the authorized refund
   intent commit together. External refund dispatch occurs afterward. A crash before
   commit rolls back both; a crash afterward leaves an executable durable intent.
7. Rejection creates a frozen draft claim. The lender may submit a claim within the
   deposit. Borrower consent cites the current claim version; stale consent fails.
   Rejection enters `escalated` and cannot be reversed through ordinary acceptance.
8. An independent administrator who is neither participant may adjudicate raised,
   escalated, borrower-originated and abandoned draft cases after recorded physical
   return evidence. A reason and bounded allocation are required. Borrower consent
   is a response, not deduction authority. Resolution is immutable through the
   application; database triggers require explicit payment migration, which is
   absent in the preserved historical sandbox. The administrator queue is
   `/payment-review`; API `GET /api/disputes` is admin-only.
9. One immutable refund allocation belongs to each booking. Provider confirmations
   must match the captured payment and expected amount. Unknown refunds keep the
   same idempotency payload/key. Active attempt ownership fences late responses.
   A 30-second stale-dispatch lease supports recovery. Processed success cannot
   regress. A confirmed failed Razorpay replacement needs administrator authority.
   Test dispatch requires explicit literal approval on `/payments/refunds/execute`;
   `/payments/refunds/reconcile` uses provider GETs only but can update local
   settlement, so it must not be used for a read-only audit.
10. Settlement posts once after confirmation. Clean return refunds the entire
    deposit; independent administrator review refunds deposit minus authorized deduction. A full
    deduction needs no provider refund call. Eligible cancellation reverses rent
    plus deposit. Simulated lender receivable entries never execute payouts.

## States and recovery

```text
awaiting_payment -> funded -> active -> returned -> settling -> completed
                       |         |          |
                       |         +----------+-> disputed -> settling -> completed
                       +-> eligible cancellation -> settling -> cancelled

dispute: needs_claim -> raised -> borrower response -> independent admin -> settled_arbitrated
               |         +-> rejected -> escalated -----------^
               +--------------------------------------------^
```

The legacy `POST /borrow-requests/{id}/return` returns 410 for managed rentals;
it cannot set `returned_at` ahead of return evidence. Generic dispute reports
create the same financial dispute/freeze as the payment workflow, including
borrower-originated reports. Reported handover issues require platform recovery:
resume acknowledgement, permit return photographs, or confirm pre-activation item
recovery and authorize cancellation. No unilateral party action dismisses an issue.

The physical rental and financial settlement retain separate statuses: approved
return does not claim successful refund before provider confirmation. Cancelled
records remain privately accessible through `GET /api/payments/requests/{id}/rental`.
The frontend loads that protected detail before rendering recovery controls.

## Configuration and deployment

| Variable | Meaning |
| --- | --- |
| `PAYMENT_PROVIDER` | `disabled` (default), `mock`, or `razorpay_test`; never silent fallback |
| `PAYMENT_DEMO_MODE` | Must be `true` for mock |
| `DEPLOYMENT_EXPOSURE` | `local` or `public`; production/prod is always treated as public |
| `APP_ENV` | Deployment environment; independent of payment selection |
| `JWT_SECRET` | Privately generated signing secret; public deployments reject known/weak values |
| `AUTO_MIGRATE` | Defaults false; importing the application performs no schema writes |
| `DATABASE_URL` | Application DB; automated tests replace it with generated isolated databases |
| `RENTAL_EVIDENCE_DIR` | Private local directory outside public `UPLOAD_DIR` |
| `RAZORPAY_KEY_ID` | Empty unless configuring Razorpay; only `rzp_test_...` accepted |
| `RAZORPAY_KEY_SECRET` | Server-only test credential |
| `RAZORPAY_WEBHOOK_SECRET` | Server-only test webhook secret |
| `PUBLIC_BASE_URL`, `CORS_ORIGINS` | Must use loopback URLs in local exposure |
| `PAYMENT_TEST_POSTGRES_URL` | Optional dedicated localhost `neighborlend_test_*` DB for isolated integration tests |

Disabled mode starts without gateway credentials and preserves authorized reads,
evidence retrieval, dispute adjudication and durable cancellation/refund intent
preparation. It rejects order, capture and provider refund dispatch. Restoring the
same booking provider enables its authorized dispatch; changing selection never
converts a booking's provider snapshot.

Mock mode is rejected for public/production deployments. Local exposure is enforced
on incoming requests: direct loopback client and host only, no forwarded/proxy
headers. Bind Uvicorn to `127.0.0.1`, with proxy-header processing disabled. Do not put
a public reverse proxy or tunnel in front of the mock application. Public demo
mocking is deliberately unsupported; deploy disabled payments instead.

Render now explicitly selects public exposure with disabled payments. Compose also
defaults to disabled payments and public exposure. Their signing/DB requirements
remain intact. Existing deployment schemas must be prepared independently; startup
does not silently migrate them. Do not apply version 2 to an existing deployment
until its migration/locking tests pass on isolated PostgreSQL and backups exist.

## Exact local mock setup (PowerShell)

Use the existing environment containing the repository's backend requirements.
The example below uses the interpreter already present in this workspace. No
dependency installation is required by this implementation.

```powershell
Set-Location D:\neighborlend_project\NeighborLend\backend
$paymentPython = 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe'
$env:PYTHONPATH = (Join-Path (Get-Location) '.test-tools')
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:APP_ENV = 'demo'
$env:DEPLOYMENT_EXPOSURE = 'local'
$env:PAYMENT_PROVIDER = 'mock'
$env:PAYMENT_DEMO_MODE = 'true'
$env:AUTO_MIGRATE = 'false'
$env:JWT_SECRET = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$demoDirectory = Join-Path (Get-Location) '.payment-demo'
$env:DATABASE_URL = 'sqlite:///' + (Join-Path $demoDirectory 'demo-v2.sqlite3').Replace('\', '/')
$env:UPLOAD_DIR = Join-Path $demoDirectory 'public-uploads'
$env:RENTAL_EVIDENCE_DIR = Join-Path $demoDirectory 'private-evidence'
$env:PUBLIC_BASE_URL = 'http://127.0.0.1:8000'
$env:CORS_ORIGINS = 'http://127.0.0.1:5173,http://localhost:5173'
$env:RAZORPAY_KEY_ID = ''
$env:RAZORPAY_KEY_SECRET = ''
$env:RAZORPAY_WEBHOOK_SECRET = ''
$env:SUPABASE_URL = ''
$env:SUPABASE_SERVICE_ROLE_KEY = ''
$demoPassword = Read-Host 'New local demo password (12-72 UTF-8 bytes)' -AsSecureString
$env:PAYMENT_DEMO_PASSWORD = [System.Net.NetworkCredential]::new('', $demoPassword).Password
& $paymentPython -B scripts/create_payment_demo.py
Remove-Item Env:PAYMENT_DEMO_PASSWORD
& $paymentPython -B -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Check that seeding succeeds before starting Uvicorn. The seeder refuses existing
files and writes only beneath `backend/.payment-demo`. It creates verified lender,
borrower and administrator accounts at `lender@neighborlend.test`,
`borrower@neighborlend.test`, and `admin@neighborlend.test`, with the password entered
privately above. It sends no email. Subsequent starts reuse the DB and private JWT
secret and skip the seeding command. An empty disabled-payment demo schema can be
prepared with `scripts/prepare_payment_database.py --new-local-demo`; this also
refuses existing files.

```powershell
Set-Location D:\neighborlend_project\NeighborLend\frontend
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000/api'
npm run dev -- --host 127.0.0.1 --port 5173
```

Use separate browser profiles for the three roles. Negotiate two days at INR
200/day with INR 500 deposit (90,000 paise total), simulate success, upload handover
evidence, acknowledge receipt, confirm handover, and upload return evidence.
Demonstrate three separate rentals: clean return (50,000-paise refund), accepted
20,000-paise claim (30,000-paise refund), and rejected claim (frozen until an admin
records a reason and allocation). Use the admin queue for abandoned claims/issues.

## Later Razorpay Test Mode activation

Set `PAYMENT_PROVIDER=razorpay_test`, `RAZORPAY_KEY_ID=rzp_test_...`,
`RAZORPAY_KEY_SECRET` and `RAZORPAY_WEBHOOK_SECRET` privately on the server. Use a
new booking. Missing/invalid credentials fail closed; live keys are rejected even
when another provider is selected. Neither secret is returned to the browser.

The allowlisted API is `https://api.razorpay.com/v1/`; Razorpay uses the same fixed
hostname for test/live APIs and the test key selects Test Mode. There is no
invented sandbox hostname or environment host override. Checkout.js loads only on
explicit test checkout. Configure dashboard capture policy and HTTPS webhooks at
`/api/payments/webhook`. Supported events are payment captured/authorized/failed,
order paid and refund processed/failed. Raw-body HMAC and durable receipt hashes
protect ingestion; authoritative reads and financial operation keys make effects
replay-safe. Timestamp freshness is not substituted for durable idempotency.

Actual hosted checkout, dashboard delivery/capture and test gateway refunds remain
unverified without credentials. Synthetic adapter tests are not gateway acceptance.

## Verification commands and boundaries

```powershell
# backend, using the interpreter above
& $paymentPython -B scripts/verify_payments.py
# frontend
npm test
npm run build
```

The backend runner isolates DBs, temp files, provider fixtures, upload storage and
artifacts. Results are written to `backend/.payment-verification/backend.xml`.
Concurrency regressions use real SQLite database transactions and threads; only
provider I/O is replaced. PostgreSQL tests are separately collected and explicitly
skip without `PAYMENT_TEST_POSTGRES_URL`. When configured, they create a UUID schema
only inside an allowlisted local dedicated test database and remove that schema
afterward. They never read the application DB URL for connectivity.

The frontend suite covers checkout contracts and failures, private evidence upload,
disabled mode, unauthorized controls, cancellation/refund recovery, escalated claims
and administrator reasons. These are Node/static-render tests, not full browser
automation. Consult the final verification results below for executed counts.

## Remaining limits

- No actual escrow custody, live financial processing, lender payout or bank transfer.
- No actual Razorpay test execution without test credentials.
- PostgreSQL runtime/migration verification requires the isolated service; unavailable
  Docker/local service is a verification blocker, not a claimed pass.
- EP reports remain advisory unverified references; no automatic model/worker
  invocation, fabricated report retrieval, or financial authority was introduced.
- Private evidence is local filesystem storage. Public deployments need persistent
  private storage, filesystem access controls, backup and retention policies. Newly
  uploaded evidence is content-hashed and authorization-bound; historical public
  photographs cannot retroactively be made private or proven authentic.
- Reconciliation is explicit through authenticated APIs/UI and provider redelivery.
  In-app notifications are committed with financial events; no automatic scheduler,
  email-delivery guarantee or unattended financial worker is claimed.
- Human administrators can record bounded test settlement decisions; the software
  does not prove physical item identity, damage causation or correctness of judgment.

## Historical executed results — 9 November 2026

| Check | Executed result |
| --- | --- |
| Full backend: `python -B scripts/verify_payments.py` | **120 passed, 3 skipped, 0 failures**, 153.84 seconds |
| Frontend: `npm test` | **23 passed, 0 failures**, 1.13 seconds |
| Frontend: `npm run build` | **Passed**, 1,656 modules, 1.13 seconds |
| Scoped payment-module/test Ruff check and format | Passed after import cleanup; exact scope is listed below |
| Existing integration modules syntax/undefined-name check | **Passed** (`E9,F821,F822,F823`); full legacy lint has seven pre-existing unused imports |
| PostgreSQL | **Not executed**: Docker daemon unavailable; no local PostgreSQL tools/service found. Three integration cases skipped explicitly |
| Razorpay gateway | **Not executed**: no test credentials; all adapter tests replace only transport |
| Browser automation | Not executed; frontend evidence is Node tests, static rendering and build |

Backend warning: the existing Starlette TestClient/HTTPX deprecation. No dependency
changes were made to suppress it. Earlier intermediate runs exposed a localhost
test-configuration mismatch and an environment-dependent default-provider test;
both were corrected before the complete passing run above. No failing test was
disabled or weakened. Existing handover fixtures now use actual private uploads,
and activation assertions follow the required two-party acknowledgement sequence.

The regression suite includes exact-version consent, stale consent rejection,
all uncaptured handover mutations, disabled-provider preservation, public-mock
rejection, weak JWT rejection, generic/borrower disputes, abandoned drafts,
post-receipt handover recovery, cancelled-record privacy, order definite-failure
recovery, delayed order completion, concurrent capture, active/stale refund leases,
late pending refund fencing, refund overpayment/mismatched payment rejection,
repeat settlement and immutable allocations. Crash injection proves return approval
and refund intent roll back together. Existing tests also cover partial/zero refund,
signature/amount/currency mismatch, webhook deduplication and gateway refund recovery.

Full Ruff scope: `app/payment_models.py`, `app/services/payments.py`,
`app/services/razorpay_service.py`, `app/services/rental_evidence.py`,
`app/services/payment_migrations.py`, `app/routers/payments.py`,
`app/routers/disputes.py`, `app/schemas/payment.py`,
`scripts/prepare_payment_database.py`, `tests/test_payment_regressions.py`,
`tests/test_postgres_payments.py`. These are the maintained payment-domain modules;
the check does not claim the entire historical repository is lint-clean.

## Files changed in this repair pass

All paths below are relative to `NeighborLend/`. Pre-existing uncommitted and
untracked work was preserved; no commit, database reset or destructive Git action
was performed.

| Paths | Purpose |
| --- | --- |
| `backend/app/config.py`, `backend/app/main.py` | Disabled default, explicit exposure, guarded startup, inert import, optional migration switch |
| `backend/app/payment_models.py`, `backend/app/models.py` | Evidence records, operation fencing, versioned claims, agreed offer/condition snapshots |
| `backend/app/services/payments.py` | Canonical return/dispute/issue transitions, consent version, durable authorization, notifications and fencing |
| `backend/app/services/razorpay_service.py` | Disabled provider, configuration validation, live-key rejection, definite failure classification |
| `backend/app/services/payment_migrations.py` | Additive version 2 columns/entity, immutable terms/decisions and terminal-state database guards |
| `backend/app/services/rental_evidence.py` | Private bounded image validation/storage, provenance and content integrity |
| `backend/app/services/negotiation.py` | Exact paise offer snapshots |
| `backend/app/routers/payments.py` | Private evidence APIs, protected cancelled/active rental reads, disabled reconciliation inspection |
| `backend/app/routers/disputes.py` | Administrator queue, issue recovery, reason/version request contracts |
| `backend/app/routers/chat.py`, `backend/app/schemas/chat.py` | Full pre-acceptance obligation contract and snapshot enforcement |
| `backend/app/routers/borrow_requests.py`, `backend/app/schemas/borrow_request.py` | Canonical managed returns/disputes, payment gates, acknowledgement sequence, private evidence and notes |
| `backend/app/schemas/payment.py` | Cancellation simulation, versioned consent, administrator reasons, issue recovery schema |
| `backend/scripts/create_payment_demo.py` | Isolated three-role demo seeding with administrator |
| `backend/scripts/prepare_payment_database.py` | Explicit new-local-demo schema preparation |
| `backend/scripts/verify_payments.py`, `backend/tests/conftest.py` | Isolated verification lifecycle and artifacts; no app-import migration |
| `backend/tests/test_payment_regressions.py`, `backend/tests/test_postgres_payments.py` | Audit regressions and optional real PostgreSQL cases |
| `backend/tests/test_razorpay_escrow.py`, `backend/tests/test_handover.py` | Real private-upload fixtures, versioned consent, optional PostgreSQL fixture and acknowledgement assertions |
| `backend/tests/test_payment_providers.py`, `backend/tests/test_payment_demo.py` | Explicit provider fixtures and three-role seed assertions |
| `frontend/src/components/PaymentModal.jsx`, `frontend/src/components/paymentFlow.js` | Mock cancellation, evidence upload contract and authorized control selection |
| `frontend/src/components/EscrowStatusCard.jsx`, `frontend/src/components/DisputeResolutionModal.jsx` | Disabled/cancelled recovery, escalation, reasons, versioned consent, issue review and audit display |
| `frontend/src/components/PaymentReviewQueue.jsx`, `frontend/src/components/RentalEvidenceImage.jsx` | Administrator discovery and authenticated blob-image rendering |
| `frontend/src/components/payments.test.js` | Expanded UI/security/contract regressions |
| `frontend/src/App.jsx`, `frontend/src/components/Navbar.jsx` | Protected administrator review navigation |
| `frontend/src/pages/Chat.jsx`, `frontend/src/pages/BorrowRequestDetail.jsx` | Complete terms, private evidence, private rental recovery and refreshed lifecycle |
| `.env.example`, `.gitignore`, `render.yaml`, `compose.yaml` | Safe disabled deployment defaults and private/generated artifact exclusions |
| `README.md`, `AGENTS.md`, `docs/payment-escrow-implementation.md`, `docs/payment-escrow-architecture-audit.md`, `docs/payment-system-verification.md` | Current behavior, superseded historical references, setup and evidence |

Local mock demonstration is verified through authenticated API/database integration.
Actual browser click-through and gateway acceptance remain unverified. Real-money
production readiness is intentionally unsupported.
