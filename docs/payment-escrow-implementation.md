# Payment and simulated escrow implementation / setup

> **Historical handoff, superseded on 2026-11-09.** Use
> [the current payment implementation and verification guide](payment-system-verification.md)
> for repaired lifecycle behavior, disabled/default mode, private evidence,
> administrator escalation, current setup and executed results. The commands and
> verification claims below describe the earlier November 8 implementation.

Verified on 2026-11-08, native Windows. Primary blueprint:
[payment-escrow-architecture-audit.md](payment-escrow-architecture-audit.md).

**Local mock implementation is verified. Razorpay Test Mode is implemented and tested
with synthetic HTTP responses, but has not been verified against Razorpay.** No gateway
request or real payment was made. Simulated deposit accounting is not regulated escrow;
simulated lender credits do not execute payouts. The EP engine, its tests, models,
photographs and exploratory artifacts were not modified or evaluated.

## Six-milestone delivery

| Milestone | Implementation and integration |
| --- | --- |
| 1. Models and schemas | Proposed `RentalBooking`, `PaymentTransaction`, `EscrowLedgerEntry`, `RentalDispute` and `ProcessedWebhook` entities are retained. Added journal headers, refund intents/attempts and financial audit records. Accepted offers snapshot dates, duration, integer-paise daily rate, rent, deposit, total, participants and provider. |
| 2. Provider and orders | Explicit `mock` and `razorpay_test` providers; deterministic mock outcomes; durable order operations; borrower-only order creation; immutable server-calculated amounts. |
| 3. Verification and webhooks | Original-order HMAC, authoritative order/payment reads, amount/currency/association checks, raw-body webhook verification, durable receipt and event deduplication. Callbacks and webhooks use the same capture transition. |
| 4. Journal and rental gates | Balanced, append-only journal; separate rent/deposit liabilities; payment capture gates photo-backed handover routes; accepted-offer integration and overlap checks retained. Legacy unpaid rentals remain locked. |
| 5. Disputes and refunds | Lender claims, frozen deposits, borrower response, exact mutual agreement or server-authorized administrator decision, bounded deductions, persistent refund intent/attempt records and reconciliation. Pre-receipt cancellation refunds rent plus deposit. |
| 6. Frontend and verification | Existing chat acceptance leads to rental detail with checkout, deposit status, claim/consent controls, refund recovery and transaction/journal display. All payment views carry test-mode notices. Native backend/API and frontend tests plus production build passed. |

## Accounting and concurrency

Amounts are integer paise. Existing Float catalog/offer fields are converted with
`Decimal(str(value))` and `ROUND_HALF_UP`; invalid values and inconsistent agreed totals
are rejected. Posted journal headers must have equal positive debit/credit totals, matching
their actual lines. Database triggers reject changes/deletion of posted financial records
and booking snapshots. ORM guards also protect snapshots and approved refund allocations.

For a two-day rental at INR 200/day with INR 500 deposit:

| Event | Debits, paise | Credits, paise |
| --- | --- | --- |
| Capture | Gateway clearing 90,000 | Rental liability 40,000; held deposit 50,000 |
| Clean return | Rental liability 40,000; held deposit 50,000 | Gateway clearing 50,000; simulated lender receivable 40,000 |
| Dispute freeze | Held deposit 50,000 | Frozen deposit 50,000 |
| Human-approved INR 200 deduction | Rental liability 40,000; frozen deposit 50,000 | Gateway clearing 30,000; simulated lender receivable 60,000 |

The last line replaces clean settlement in the disputed example. Cancellation after
funding but before receipt refunds all 90,000 paise and creates no lender receivable.
Deposit refunded + authorized deduction + remaining deposit equals the original deposit.
Pending, failed or unknown refunds retain the deposit liability; successful settlement is
posted once, only after confirmation. A full-deposit deduction permits a zero refund
without making an unnecessary provider call.

SQLite financial operations use `BEGIN IMMEDIATE`; PostgreSQL uses booking row locks.
Lifecycle mutations lock booking before rental to keep the lock order consistent. Offer
acceptance serializes on the listing before checking overlap. Unique operation references
and journal references prevent duplicate funding/settlement. Provider calls run outside
database transactions, after durable operation intent commits.

An uncertain order creation is reconciled by its saved receipt; it is never blindly
recreated. Unknown refund outcomes reuse the exact payload and `X-Refund-Idempotency`
key. Known refunds are fetched by ID. An active refund dispatch blocks competing dispatch;
stale dispatch recovery has a 30-second lease. A replacement for a known failed Razorpay
refund requires administrator authorization and authoritative confirmation of terminal
failure; previous attempt/transaction history remains recorded.

## Provider selection and API

`PAYMENT_PROVIDER=mock` additionally requires `PAYMENT_DEMO_MODE=true` and an explicit
development/test/demo/local environment. `MOCK_PAYMENTS` is deprecated and grants no
authority. Both implemented providers reject production environments; invalid configuration
fails closed. A booking retains its provider snapshot; changing the configured provider
does not convert an existing booking. Create a new booking for a different provider.

All financial endpoints require the existing bearer JWT and object-level authorization,
except the separately signed webhook. Financial responses use `Cache-Control: no-store`.
Amounts are not accepted from checkout clients. Important routes:

| Route under `/api` | Purpose / authority |
| --- | --- |
| `GET /payments/by-request/{request_id}` | Participant/admin summary, transaction history, journal and refund/dispute status |
| `GET /payments/bookings/{booking_id}` | Same protected financial summary |
| `POST /payments/create-order` | Borrower; `{booking_id}` |
| `POST /payments/mock-confirm` | Mock borrower only; `{booking_id, outcome: success/failed/pending, payment_id?}` |
| `POST /payments/verify` | Borrower; `{booking_id, order_id, payment_id, signature}` |
| `POST /payments/reconcile` | Participant payment recovery; `{booking_id}` |
| `POST /payments/cancel` | Participant, before receipt; `{booking_id}`; creates eligible refund intent |
| `POST /payments/refund-deposit` | Lender-approved clean return only; `{booking_id}` |
| `POST /payments/refunds/reconcile` | Execute/reconcile an existing authorized intent; `{booking_id}`; mock additionally accepts `demo_outcome` |
| `POST /payments/refunds/reconcile` with `retry_failed:true` | Administrator-only replacement of a confirmed failed Razorpay refund |
| `POST /disputes/raise` | Lender; `{booking_id, claimed_deduction_paise, reason, inspection_id?, cv_run_id?, assessment_id?}` |
| `POST /disputes/respond` | Borrower; `{booking_id, accepted, notes?}` |
| `POST /disputes/settle` | Exact borrower-accepted amount or administrator; `{booking_id, approved_deduction_paise}` |
| `POST /payments/webhook` | Raw signed provider event; `X-Razorpay-Signature` and `X-Razorpay-Event-Id` required |

Return approval uses the existing `/borrow-requests/{id}/return/confirm` endpoint. Human
rejection creates a frozen `needs_claim` draft; its initial zero amount is not borrower
consent or a settlement decision. AI reference UUIDs are advisory, unverified references:
this implementation neither retrieves EP reports nor invents findings. No AI field can
authorize financial action. Existing physical evidence remains in the application's
existing rental workflow, with its existing storage/access limitations.

## Exact local mock startup (PowerShell)

Use a **new isolated demo database**, rather than the existing application database.
The seed command refuses an existing file and creates two verified local accounts and
a published INR 200/day listing with INR 500 deposit. It sends no email.

Backend terminal:

```powershell
Set-Location D:\neighborlend_project\NeighborLend\backend
$paymentPython = 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe'
$env:PYTHONPATH = (Join-Path (Get-Location) '.test-tools')
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:APP_ENV = 'demo'
$env:PAYMENT_PROVIDER = 'mock'
$env:PAYMENT_DEMO_MODE = 'true'
$env:JWT_SECRET = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$demoDir = Join-Path (Get-Location) '.payment-demo'
$env:DATABASE_URL = 'sqlite:///' + (Join-Path $demoDir 'demo.sqlite3').Replace('\', '/')
$env:UPLOAD_DIR = Join-Path $demoDir 'uploads'
$env:PUBLIC_BASE_URL = 'http://127.0.0.1:8000'
$env:SUPABASE_URL = ''
$env:SUPABASE_SERVICE_ROLE_KEY = ''
$env:CORS_ORIGINS = 'http://127.0.0.1:5173,http://localhost:5173'
$demoPassword = Read-Host 'New local demo password (12-72 UTF-8 bytes)' -AsSecureString
$env:PAYMENT_DEMO_PASSWORD = [System.Net.NetworkCredential]::new('', $demoPassword).Password
& $paymentPython -B scripts/create_payment_demo.py
Remove-Item Env:PAYMENT_DEMO_PASSWORD
& $paymentPython -B -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run the seed command only for initial creation. On subsequent starts export the same
configuration, skip seeding and reuse the demo database; keep a stable private JWT secret
if existing sessions should remain valid. Check the seed command succeeded before
starting the server. Existing root `.env` is unchanged; exported values override it.
The application's existing YOLO preload remains part of normal startup; no EP worker is
started by this payment implementation.

Frontend terminal:

```powershell
Set-Location D:\neighborlend_project\NeighborLend\frontend
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000/api'
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173`. In separate browser sessions sign in as
`lender@neighborlend.test` and `borrower@neighborlend.test` using the password entered
above. Negotiate a two-day rental at INR 200/day; accept the offer; pay the 90,000-paise
mock order in rental detail. Handover stays locked until capture. Complete lender photos,
borrower receipt and lender confirmation, then borrower return photos. Lender approval
refunds 50,000 paise. On a separate booking, submit a 20,000-paise claim, obtain the
borrower's explicit agreement, authorize the matching settlement and execute/reconcile
the 30,000-paise refund. Mock pending/failed controls demonstrate recovery without money.

## Razorpay Test Mode setup (future, credential-dependent)

Use a new booking after setting `PAYMENT_PROVIDER=razorpay_test`, `APP_ENV=demo`,
`RAZORPAY_KEY_ID=rzp_test_...`, `RAZORPAY_KEY_SECRET` and `RAZORPAY_WEBHOOK_SECRET` in
the server environment. Never use live keys. No silent fallback exists. Secrets remain
server-side; checkout receives only the public test key, original order and server amount.
Checkout.js loads lazily on an explicit Razorpay checkout action; mock mode never loads it.

Configure the Test Mode dashboard capture policy and an HTTPS webhook URL ending in
`/api/payments/webhook`. Supported events are `payment.captured`, `payment.authorized`,
`payment.failed`, `order.paid`, `refund.processed` and `refund.failed`. Authorized-only
payments do not unlock handover. Use the dashboard's event identifier and raw-body HMAC.
The official API uses the same fixed HTTPS hostname in test/live modes; the credential
selects the mode, so there is no invented sandbox hostname. This adapter accepts only
test-key configuration and checks authoritative payment data.

Real hosted checkout, dashboard capture/webhook delivery, gateway reconciliation and
refunds require future authorized Test Mode execution. They were not exercised here.

## Executed verification

Final verification was necessary because payment recovery/security edits followed the
earlier 78-test pass. All tests used isolated databases and synthetic financial/provider
fixtures. No existing application database migration was executed.

| Check | Executed command / result |
| --- | --- |
| Full backend | From `backend/`: `& $paymentPython -B scripts/verify_payments.py` — **84 passed, 0 failed, 0 skipped**, 85.14 seconds |
| Frontend | From `frontend/`: `npm test` — **16 passed, 0 failed, 0 skipped**, 578.482 ms |
| Production build | From `frontend/`: `npm run build` — **PASS**, 1,654 modules, 20.00 seconds |
| Ruff | Format plus `ruff check` on the 14 payment modules/scripts/tests listed below — **PASS** |
| Migration / domain | Repeat additive migration, journal database guards, immutable snapshots, exact paise conversion and legacy records tested on isolated SQLite |
| Connected mock scenarios | Authenticated offer acceptance → order → capture → handover → return → clean refund; human-approved partial settlement; full deduction/zero refund; pre-receipt cancellation; delayed/failed payment and refund recovery |
| Essential recovery | Concurrent settlement reuses one intent; uncertain order creation reconciles without a second POST; unknown refunds retain the same key; known failed Razorpay replacement requires administrator authority; duplicate capture/webhook and out-of-order events do not duplicate settlement |

Five backend warnings remain: existing Starlette TestClient HTTPX deprecation and four
Pydantic `min_items`/`max_items` deprecations. No dependency upgrades were made to suppress
them. Backend JUnit output: `backend/.payment-test-artifacts/backend.xml`. Coverage was
not measured for this payment task; no coverage claim is made.

Reproduce the scoped lint check from `backend/`:

```powershell
$paymentFiles = @(
  'app/payment_models.py', 'app/routers/payments.py', 'app/routers/disputes.py',
  'app/schemas/payment.py', 'app/services/escrow_service.py',
  'app/services/payment_migrations.py', 'app/services/payments.py',
  'app/services/razorpay_service.py', 'scripts/verify_payments.py',
  'scripts/create_payment_demo.py', 'tests/test_escrow_domain.py',
  'tests/test_payment_providers.py', 'tests/test_razorpay_escrow.py',
  'tests/test_payment_demo.py'
)
& $paymentPython -B -m ruff check @paymentFiles
& $paymentPython -B -m ruff format --check @paymentFiles
```

Verification subprocess sessions finished. A basic native process check initially found
only the older Node process (PID 3940, started November 6). At final handoff two Python
processes (PIDs 20076 and 24676, started 23:12:34) were also visible; ownership/command
lines could not be established with available process-query permissions. They were not
terminated. No agent verification session remains active.

## Blueprint deviations and rationale

1. **Real balanced journal:** added `JournalTransaction` headers and counter-account
   lines. The audit's examples alone were not balanced double-entry transactions. Mutable
   `running_balance_paise` rows were replaced by auditable postings and derived summaries.
2. **Recovery records:** added `RefundIntent`, `RefundAttempt` and `FinancialAudit`, plus
   explicit uncertain states. External requests cannot be atomic with local commits.
3. **Concurrency:** SQLite uses an immediate write transaction, rather than ineffective
   SQLite `FOR UPDATE`. PostgreSQL row locks and journal triggers are implemented; runtime
   PostgreSQL verification remains pending on an isolated service.
4. **Provider implementation:** secure standard-library HTTPS replaces the proposed
   Razorpay SDK, avoiding a new runtime dependency. TLS verification, fixed host, bounded
   responses, timeout and redirect/proxy restrictions remain explicit. Refund idempotency
   is provider-supported; order recovery uses receipts instead of assuming POST idempotency.
5. **Checkout loading:** lazy official Checkout.js loading replaces an unconditional
   `index.html` script so local mock mode makes no provider contact.
6. **Lifecycle safety:** legacy unfunded records are not backfilled as paid. Two obsolete,
   broken handover aliases return 410 after authorization/payment checks; use the existing
   photo-backed workflow. Fixed return confirmation's pre-existing incorrect lender check.
7. **Human authority:** an AI flag never opens a financial settlement automatically.
   Rejection freezes a draft claim; explicit claim/consent or administrator authority is
   required. EP integration is reference-only, with no engine modification or fabricated
   report retrieval.
8. **Test dependencies:** missing existing backend dependencies were installed only in
   approved `backend/.test-tools/`; Conda packages were unchanged. Frontend dependencies
   were restored using approved `npm ci --ignore-scripts`, preserving the lockfile.

Official protocol references consulted during implementation:
[refund idempotency](https://github.com/razorpay/markdown-docs/blob/master/api/refunds/normal-refunds-idempotent.md),
[webhook delivery](https://github.com/razorpay/markdown-docs/blob/master/webhooks/best-practices.md),
[checkout verification](https://d6xcmfyh68wv8.cloudfront.net/docs/payments/payment-gateway/web-integration/standard/build-integration/).

## Changed files and remaining limits

New backend: `app/payment_models.py`, `app/routers/{payments,disputes}.py`,
`app/schemas/payment.py`, `app/services/{escrow_service,payment_migrations,payments,razorpay_service}.py`,
`scripts/{verify_payments,create_payment_demo}.py`, `pyproject.toml`, and
`tests/{test_escrow_domain,test_payment_providers,test_razorpay_escrow,test_payment_demo}.py`.
Existing backend integration: `app/{config,database,main,models}.py`,
`app/routers/{chat,borrow_requests}.py`, `tests/{conftest,test_handover}.py`.

New frontend: `src/components/{PaymentModal,EscrowStatusCard,DisputeResolutionModal}.jsx`,
`PaymentModal.css`, `paymentFlow.js`, `payments.test.js`, and
`scripts/{register-payment-tests,payment-test-loader}.mjs`.
Existing frontend integration: `package.json`,
`src/pages/{Chat,BorrowRequestDetail,ListingDetail}.jsx`.
Root changes: `.env.example`, `.gitignore`; this report is new. Actual `.env`, root CI,
existing user databases, and EP files were not edited.

The additive migration creates financial tables/triggers and upgrades missing recovery
columns without rewriting legacy rental data; execution is verified on isolated SQLite.
Back up and test migration on a separate copy before using an existing deployment.
PostgreSQL trigger/concurrency execution, real gateway credentials, and a full browser
click-through were not verified. Frontend verification covers checkout logic, mocked hosted
widget outcomes, rendered states and the production build, not browser automation.

Historical webhooks for an older terminal-failed refund after replacement may require
manual review; unknown associations remain unprocessed rather than settling another
booking. Provider uncertainty intentionally requires reconciliation/operator attention.
The existing generic dispute-note flow is not itself a financial settlement decision.
Active rentals require return review; there is no unilateral active-rental cancellation.
No new automatic administrative alerts, real lender payouts, regulated escrow,
production payments or direct EP report integration are claimed.
