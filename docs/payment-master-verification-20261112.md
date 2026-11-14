# Payment implementation and verification — 12 November 2026 (IST)

JWT follow-up: the later [authentication audit](jwt-security-verification-20261112.md)
removes the fallback and verifies the user's separately provisioned private key.
The signing-key observations below describe the earlier payment audit's state.

**The existing payment subsystem was extended and the shared Supabase financial
schema is applied and verified.** Hosted schema changes followed the user's
explicit instruction to create and show the tables. No fresh Razorpay financial
mutation, external deployment, lender payout or historical settlement mutation
was performed. New hosted financial tables are intentionally empty.

## A. Architecture

Existing FastAPI routers continue to use `PaymentService`, the provider adapters,
booking locks and journal. Accepted `negotiation_offers` create `borrow_requests`
rentals with one unique `rental_bookings` commercial snapshot. Application varchar
IDs, existing float display fields, handover/return/evidence, notifications and
the AI/EP engines/checkpoints are preserved.

| Requested logical responsibility | Reused implementation |
| --- | --- |
| Immutable commercial payment order | Booking snapshot + order rows in `payment_transactions` |
| Verified captures | Payment transaction rows, unique provider IDs, one capture per booking |
| Security deposits | Immutable booking principal + posted liability ledger + authorized refund allocation |
| Refunds | `refund_intents`, `refund_attempts`, refund transaction rows |
| Journal headers/lines | `journal_transactions`, `escrow_ledger_entries` |
| Lender settlements | Existing simulated lender subledger + explicit `lender_settlement` API projection |
| Webhook inbox | `processed_webhooks`, event-ID/body-hash deduplication |

New focused services provide private receipts and eligibility for existing rating
fields. Payment status now exposes posted-ledger reconciliation, reserved refunds,
simulated lender earnings/compensation and rating eligibility. Unposted drafts do
not affect liability. There is no parallel rental/payment/rating state machine.

Checkout adds an explicit terms checkbox and verified name/email prefill. Legacy
checkout clients remain compatible through the checked accepted offer, recorded
as `legacy_accepted_offer`; explicit false or string consent is rejected. New
clients record `checkout_confirmation`. Revised admin decisions require the
current claim version. Legacy admin clients work only with version-one claims.
The UI freezes stale forms until updated evidence is reviewed and a new reason
is entered. An explicit reject-claim button authorizes a zero deduction.

Ratings fixes: return confirmation alone cannot permit ratings before settlement;
resolved disputes can become eligible; lender rating authorization compares the
actual lender ID; aggregate increments are atomic. Duplicate/wrong-party ratings
are rejected. Existing completed legacy rentals retain their earlier rating
contract without being represented as provider-funded rentals.

## B. Supabase and migrations

The actual configured hosted catalog was inspected in a **read-only transaction**:
columns/defaults/types, constraints/FKs, indexes, enums, triggers, RLS, grants and
history. The Supabase app connection listed different projects; no unrelated
project was changed. Original public tables: `users`, `listings`, `listing_photos`,
`borrow_requests`, `negotiation_offers`, `conversations`, `messages`, `notifications`,
`email_verifications`, `captcha_challenges`. They had 26 constraints, RLS enabled,
no application triggers and no financial tables/history.

The existing `migrate_payments` / `payment_schema_versions` history was extended.
Alembic is installed but inactive; no competing Supabase CLI history was created.
Installed CLI **2.58.5** and actual command help were checked. The
[CLI v3 targeting change](https://supabase.com/changelog/supabase-cli-v3) was
reviewed; the CLI was not upgraded and no v3 flags were guessed.

The cumulative migration is
[`003_supabase_financial_guards.sql`](../backend/migrations/payments/003_supabase_financial_guards.sql).
It creates ten financial tables plus the version table, adds six nullable offer
snapshot columns and two nullable return-note columns, installs indexes and
binding/allocation/immutability/balance guards, enables RLS, and revokes browser
financial access. Existing enums, price types and row values are unchanged. Old
offers are not silently backfilled or reaccepted.

Applied SHA-256:
`dafb8949ea0befcedb059a1197b108bdfc3f46a80963d0f3364bdd33e01edae8`.

An official EDB **PostgreSQL 17.11** binary distribution ran in a generated
loopback-only cluster, using dedicated `neighborlend_test_*` databases. Hosted
catalog definitions were replayed locally **without hosted rows**. The Python
migrator passed twice. Independently exported SQL passed twice against another
original-schema reconstruction; all ORM columns were selectable afterward.
RLS and table/function browser-denial checks passed. Real PostgreSQL tests
covered capture/refund concurrency, return/dispute races and invalid mutations.

Following explicit authorization, preflight verified original schema, row
fingerprints and backend `BYPASSRLS` capability. A custom-format public backup
was created and its archive verified before the exact SQL was applied atomically.
An independent post-migration catalog query then confirmed the hosted result.

**Hosted status: APPLIED / VERIFIED.** Public contains **21 tables, 77 constraints
and 18 application triggers**. Original row counts and original-column hashes
are unchanged. All ten financial tables are empty; version history has two rows
(2 and 3). RLS is enabled and direct browser financial access is denied. View
[the table inventory/diagram](supabase-payment-tables.md) or
[Supabase Table Editor](https://supabase.com/dashboard/project/lgurfoppprubxbclpoqk/editor).

Exact executed command, from `backend/`:

```powershell
& 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe' -B scripts/apply_payment_schema.py --apply --sha256 dafb8949ea0befcedb059a1197b108bdfc3f46a80963d0f3364bdd33e01edae8
```

Do not rerun the initial-application wrapper: its preflight rejects schema drift.
Future hosted changes require another reviewed migration/authorization. Importing
the app remains inert (`AUTO_MIGRATE=false`). Newly created disposable webhook
stacks now install financial guards; historical stacks were not migrated.

Lock/data impact: nullable additions briefly lock the two existing tables without
rewriting their values. Lock waits are bounded to 5 seconds and statements to 60
seconds; initial financial indexes run on empty tables. Failure before COMMIT
rolls back the migration. After successful use, prefer a reviewed forward fix.
The private backup is an operator-controlled recovery option; do not restore it
destructively over shared state without approval and an isolated restore rehearsal.

## C. Razorpay

Existing code provides genuine Checkout, server orders, stored-order HMAC plus
provider capture reads, full/partial durable refunds, reconciliation, webhook
signatures/deduplication and unknown-outcome recovery. Callback success cannot
unlock handover. Client amounts and AI financial authority remain rejected.
Only verified name/email are prefills; unverified phone details are omitted.

Six fresh authenticated **GET-only** reads confirmed two historical Test scenarios:
both payments are captured for 250000 paise; the associated refunds remain
processed for 200000 and 140000 paise. A transport guard rejected non-GET methods.
These reads verify credentials/historical provider state; **they do not prove a
new Supabase-backed checkout**. No historical financial records were mutated.

Fresh provider order creation, Checkout and refund dispatch using hosted financial
records remain **NOT VERIFIED / awaiting separate financial authorization**.
Genuine external webhook delivery is **NOT VERIFIED** in this run. Route capability
is unverified/unsupported; no lender transfer/payout is implemented. Lender
allocations remain explicitly simulated. The existing stable
`X-Refund-Idempotency` header follows the
[provider's documented contract](https://github.com/razorpay/markdown-docs/blob/master/api/refunds/normal-refunds-idempotent.md).

## D. Financial accounting

Money uses `BIGINT` paise in INR. Pricing boundaries use validated
`Decimal(str(value))`, bounds and explicit half-up rounding; existing float
display fields are not the final financial source.

| Event | Debit | Credit |
| --- | --- | --- |
| ₹2,500 captured | Gateway clearing ₹2,500 | Rental clearing/payable ₹500; deposit liability ₹2,000 |
| Dispute hold | Deposit held ₹2,000 | Deposit frozen ₹2,000 |
| Clean settlement | Deposit ₹2,000; rental clearing ₹500 | Gateway refund clearing ₹2,000; simulated lender payable ₹500 |
| ₹600 reviewed compensation | Frozen deposit ₹2,000; rental clearing ₹500 | Gateway refund clearing ₹1,400; simulated lender payable ₹1,100 |

The existing combined simulated lender account is retained for compatibility;
the API separates rental earnings from authorized compensation. Deposit principal
is never represented as ordinary lender earnings or a transfer to the lender.
Remaining liability derives from **posted** held/frozen ledger lines. Views report
processed refunds, allocated compensation, reserved refunds and available
unreserved liability. Pending amounts are reservations, not processed refunds.
Original deposit = processed deposit refunds + allocated compensation + remaining
liability. Journals balance before posting and cannot subsequently be edited.

Unique capture/operation/provider identities plus booking serialization prevent
repeat effects. External I/O follows committed intent, outside financial row
locks. This ledger records simulated obligations; it is not regulated escrow or
evidence of bank segregation or an actual lender transfer.

## E. Functional UI matrix

PASS means deterministic API/component/browser evidence, not a genuine gateway
click for every control in this run. Paths below are relative to `/api`.

| Component/control | Endpoint | Intended behavior and evidence |
| --- | --- | --- |
| Payment card: Refresh | GET `/payments/by-request/{id}` | Authorized view only; API tests PASS |
| Checkout: terms / Pay | POST `/payments/create-order` | Consent, fixed amount, Test order; API + browser consent PASS; fresh gateway dispatch NOT VERIFIED |
| Checkout success | POST `/payments/verify` | HMAC and independent capture; synthetic provider tests PASS |
| Checkout failure/dismiss/retry | Widget events + same order operation | No assumed funding; Node tests PASS |
| Local mock outcomes/delayed payment | POST `/payments/mock-confirm` | Isolated simulator only; tests PASS |
| Reconcile payment | POST `/payments/reconcile` | Read provider; fund once; provider tests PASS |
| Cancel before receipt | POST `/payments/cancel` | Existing authorized policy; lifecycle tests PASS |
| Download payment receipt | GET `/payments/bookings/{id}/receipt` | Capture-only private receipt; API privacy/escaping + actual browser synthetic download PASS |
| Download refund acknowledgment | GET `/payments/bookings/{id}/refund-acknowledgment` | Processed allocation only; full/partial/zero/pending tests + browser download PASS |
| Handover/return photo upload | POST `/payments/bookings/{id}/evidence?stage=...` + request upload endpoints | Private evidence, captured funding gate; regression tests PASS |
| Borrower/lender handover confirmation | POST `/borrow-requests/{id}/handover/borrower-confirm`, `/handover/lender-confirm` | Existing paired activation; handover tests PASS |
| Return photos / approve / reject | POST request `/return/upload-photos`, `/return/confirm` | Physical return then clean allocation/review; API and PG race tests PASS |
| Raise generic issue | POST `/borrow-requests/{id}/dispute` | Freeze and preserve reason; role/lifecycle tests PASS |
| Lender submit/revise claim | POST `/disputes/raise` | Versioned amount/evidence; damage-claim tests PASS |
| Borrower agree/reject claim | POST `/disputes/respond` | Current-version response, no deduction power; security tests PASS |
| Admin queue/evidence review | GET `/disputes`, booking/rental/evidence GETs | Admin/ownership authorization; API tests PASS |
| Admin approve compensation | POST `/disputes/settle` | Independent actor, reason, version, deposit bounds; stale API + browser tests PASS |
| Admin reject damage claim | Same settle endpoint, deduction 0 | Full deposit authorization; backend case and actual synthetic browser click/current version PASS |
| Handover issue recovery | POST `/disputes/handover-issue/resolve` | Existing continue/cancel/return policy; role/lifecycle tests PASS |
| Refund approval / send | POST `/payments/refunds/execute` | Literal human approval, durable intent; synthetic approval/timeout tests PASS; fresh provider mutation NOT VERIFIED |
| Refund reconcile | POST `/payments/refunds/reconcile` | Provider reads, reserve uncertainty, settle once; PG concurrency/recovery PASS |
| Admin retry confirmed failure | Execute, `retry_failed=true` | Admin plus independent failure confirmation; provider tests PASS |
| Rate lender / borrower | POST request `/rate-lender`, `/rate-borrower` | Completed return/finance, right role, once; new tests PASS |
| Timeline/audit | Booking GET | Posted balanced journals and audit; presentation tests PASS |

Documents are locally issued **Test Mode HTML**, printable/saveable as PDF through
the browser. They are not Razorpay invoices or tax invoices. They include stable
document/rental references, item/period, participant names, fee/deposit/total,
provider IDs, capture status/date, and refund allocation/reference/confirmed date.
Downloads require participant/admin authorization, use `no-store`, escape names
and omit emails, passwords, card/bank information and fabricated tax registrations.

## F. Testing and security

| Verification | Result |
| --- | --- |
| Baseline backend | 289 passed; 3 PostgreSQL skipped |
| Final complete backend, isolated PostgreSQL enabled | 312 passed; 0 failed; 0 skipped |
| PostgreSQL suite | 13 passed; includes 10 new security/concurrency cases |
| Final PostgreSQL function/table-access supplement | 10 passed |
| Frontend Node tests | 42 passed; 0 failed/skipped |
| Final Vite build | PASS; 1659 modules |
| Payment frontend lint/format | PASS |
| Changed payment Python lint/format | PASS |
| Headless Chrome | PASS: consent, changed-claim review/reset, admin reject/current version, both downloads; in-memory APIs only |
| Python migration / independent SQL against original catalog | PASS; each twice; ORM compatibility and browser denials |
| Hosted backup/apply/independent inspection | PASS; original rows preserved; 21 tables / 77 constraints / 18 triggers |
| Historical Razorpay Test checks | PASS; six GETs, two captures, two processed refunds |
| Fresh hosted Checkout/refund acceptance | NOT VERIFIED; separate authorization required |
| Supabase CLI lint/advisors | NOT VERIFIED: CLI 2.58.5 lacks advisors; lint refused the non-TLS disposable server. Independent catalog security checks passed; this is not an advisor pass |

Coverage includes duplicate capture/refund, concurrency, wrong actor/order/amount,
stale decisions, journal tampering, failed/abandoned checkout, signed duplicate and
out-of-order webhooks, timeouts/unknown outcomes, refund states, return/dispute
races, document privacy and rating eligibility/duplicates. Pytest forbids real
gateway transport. SQLite does not substitute for PostgreSQL lock/trigger evidence.

The configured signing key is still the known repository default, confirmed by
the final private configuration check; it must be replaced before public use.
The prior release audit's old `python-jose` / `python-multipart` dependency findings
also remain public-release blockers. No broad
package upgrade or secret rotation was made. Internal functions have pinned search
paths and revoked PUBLIC/anon/authenticated execute grants. Environment files are
ignored/untracked; no backend secret is introduced in frontend code. AI checkpoints
and EP files are unchanged. Full dependency security and repository-wide lint debt
are not certified by payment-scope checks. A scan of 341 source/document/built-asset
files found no configured database/provider/webhook/service-role/SMTP secret values.
The known default signing key was treated as the explicit configuration finding,
not falsely reported as a newly leaked private secret.

## G. Deployment and controlled acceptance

Keep secrets in ignored `backend/.env`: PostgreSQL connection, private signing key,
`PAYMENT_PROVIDER=razorpay_test`, Test key/secret/webhook secret,
`PAYMENT_DEMO_MODE=false`, `AUTO_MIGRATE=false`. Never put database/service-role
secrets in `VITE_*`. The inspected backend DB role has `BYPASSRLS`; it belongs
only on the server. Public deployment requires the existing public-mode checks
and a strong new signing key. Source changes were not externally deployed.

Follow the existing [webhook runbook](test-webhook-ingress.md): register a Test
HTTPS webhook URL ending `/api/payments/webhook`; preserve raw bytes, signature
and event identity. Expose only the dedicated ingress, not the private API. Verify
genuine delivery in the provider Test Dashboard. No public listener was created.

From `backend/`, use the configured Conda Python with
`-B scripts/verify_payments.py`. For PostgreSQL coverage, set
`PAYMENT_TEST_POSTGRES_URL` to a dedicated **local** `neighborlend_test_*` database;
fixtures create/drop only UUID schemas. `isolated_payment_postgres.py` starts/stops
only its recorded generated loopback cluster using extracted official runtime
binaries. `verify_postgres_master.py` replays the private catalog into an empty
local DB; `--verify-sql` checks the SQL independently. Frontend commands are
`npm test`, `npm run lint:payments`, `npm run format:payments:check`, `npm run build`.

Next financial acceptance needs explicit approval for **fresh isolated records**:
create Test orders; complete genuine Checkout; verify capture/hosted associations;
record handover/return evidence; authorize clean full-deposit and reviewed partial
allocations; explicitly send Test refunds; verify `processed`; inspect hosted
journals/documents and submit eligible ratings. Expected A/B payments: ₹2,500
each; A refunds ₹2,000; B authorizes ₹600 compensation and refunds ₹1,400. Do not
reuse historical payments, create payouts or use AI as an approver. Verify Test
webhook delivery independently. No schema approval remains pending.

## H. Outstanding blockers and evidence

Remaining permission boundary: fresh provider-side Test orders/refunds and
acceptance data. Actual Route transfers, production deployment, independent
webhook delivery and dependency/JWT release hardening remain unverified or
unsupported. No Git commit, push, merge, rebase or main-branch change occurred.

Private ignored evidence under `backend/.payment-verification/`:

- `backend.xml`: final complete suite; earlier results were replaced by the final run.
- `master-20261111/hosted-schema.json`, `hosted-schema-after.json`: before/after catalogs.
- `master-20261111/hosted-apply-0a37b15f18c54bb1937d1eef9566483c/verification.json`:
  exact SQL hash, backup verification and original-row preservation.
- The same private directory's `public-before.dump`: verified backup, containing
  private application data; never commit or publish it.
- `master-20261111/postgres.xml`, `postgres-final-guards.xml`, `new-tests.xml`:
  PostgreSQL and new behavior regressions.
- `master-20261111/browser-checks.json`, screenshots and synthetic downloads:
  actual browser interactions with all API/provider traffic blocked.
- `master-20261111/provider-readonly.json`: historical Test GET results and scope.
- `master-20261111/frontend-dist-complete/`: successful final frontend build.

Private artifact paths use the task's start date, 11 November. Completion and
hosted verification continued into 12 November IST.

The generated PostgreSQL cluster and headless browser/Vite processes were stopped
after verification. Hosted tables persist. New source and migration files remain
uncommitted in the feature-branch working tree for review and inclusion in the
eventual feature commit.
