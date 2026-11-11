# Final payment release audit — 11 November 2026 (IST)

**Academic demonstration: PASS with restrictions. Production release: FAIL.** The existing completed Test scenarios can be demonstrated under supervision on the current loopback services. This is a read-only demonstration of completed records, plus regressions in generated databases. It is not clearance for new financial operations, public application exposure, production money, lender payouts or regulated escrow. The active historical database lacks the trigger layer used in migrated regression fixtures, and the current local signing secret fails public-deployment policy.

The [current payment architecture](payment-architecture.md) describes the final implementation. This report supersedes earlier statements that the genuine A/B checkouts/refunds were still awaiting execution. Older audit artifacts remain unchanged.

## Independent provider and financial verification

Fresh verification completed at **02:59:24 IST on 11 November 2026**, equivalent to **21:29:24 UTC on 10 November**. Fourteen authenticated official Razorpay Test GETs independently fetched three orders, their payment collections, three captured payments, all three refund collections, and both individual refunds. A guard prohibited every gateway method except GET. No capture/refund execution, retry or application reconciliation was performed.

| Record | Payment, amount and capture | Refund and status | Result |
| --- | --- | --- | --- |
| Scenario A | `pay_TyajgFOh81OR9L`, 250000 paise INR, captured; order `order_TyaI49iURtfrnA` | Exactly one: `rfnd_TybBSuPBEFl7RW`, **200000 paise INR, processed**, matching payment | **PASS** |
| Scenario B | `pay_TybRJOKvo9JNwF`, 250000 paise INR, captured; order `order_TyaI58iaJg9QQ8` | Exactly one: `rfnd_TycHaMdmEPR61R`, **140000 paise INR, processed**, matching payment | **PASS** |
| Preserved original | `pay_TyZngjx2npbwTx`, 100 paise INR, captured; order `order_TyYcyFgRliMilB` | Zero provider refunds and zero local refund intents | **PASS** |

All **44** scenario/provider/accounting assertions passed. Provider order notes match booking IDs; each order has exactly one captured payment; local capture and refund IDs match the provider. Both refund receipts match immutable local intent keys. Earlier failed payment attempts and pending refund-attempt observations remain historical records and have not generated duplicate funding or refunds.

A and B are `completed` / payment `captured` / deposit `settled`, with closed borrow requests. Each has one processed local refund transaction, one immutable processed refund intent, one funding journal and exactly one settlement journal. B additionally has one deposit-freeze journal. All six journal headers across the three bookings have matching positive debit/credit line totals. The original ₹1 booking intentionally remains `funded`, with its sole 100-paise funding journal and no settlement; it was not advanced to completion.

| Settlement | Refund | Approved deduction | Rental retained | Simulated lender allocation | Journal debit = credit |
| --- | ---: | ---: | ---: | ---: | ---: |
| A, clean return | ₹2,000 | ₹0 | ₹500 | ₹500 | 250000 paise |
| B, reviewed dispute | ₹1,400 | ₹600 | ₹500 | ₹1,100 | 250000 paise |

Settlement A: journal `2470586f-1bc9-4f02-b2cb-31147d7fd7c9`, reference `settlement:b74b6ff4-91b5-41e6-b16f-6fd7a4d3ead0`. Settlement B: journal `0d24cd78-ba98-440d-b935-d3ad5bb90767`, reference `settlement:b60689be-73b2-47f2-992c-87e03dcf6303`. Deposit conservation holds: 200000 + 0 = 200000 for A; 140000 + 60000 = 200000 for B. Rental retention plus approved deduction equals each simulated lender allocation. There is no lender payout.

A's return and clean-return allocation were authorized by its lender, with borrower return evidence and lender confirmation recorded; there is no dispute. B's dispute is `settled_arbitrated`; its resolving account is an administrator distinct from both parties. Its decision, timestamp, reason, return evidence references and 60000-paise approval are recorded. The reason explicitly describes a controlled sandbox assessment and does not claim independent confirmation of actual physical damage. Borrower disagreement remains recorded and was not overwritten as consent. Each completed booking has exactly one settlement-authorization audit event and one settlement-confirmation event.

Both provider payment summaries say `refund_status=partial` because rental is retained. Both refund entities say `processed`. Neither refund remains pending. B's earlier pending attempt references the same refund ID as its processed active attempt. B's `return_photos_uploaded` physical-history field is retained, while its dispute is resolved and financial settlement completed; the UI derives the reviewed return label and suppresses a new clean-return decision.

An attempt or `refund_requested` audit event is not proof that a gateway POST occurred: the service records attempts for GET reconciliation too. Webhook recovery can use the booking borrower's ID as service context, which does not prove that the borrower clicked a button. Exactly one provider refund and one local settlement are verified; the historical number of HTTP dispatch attempts and precise UI-click provenance are not reconstructed.

## Verification matrix

| Requirement | Result | Evidence / limit |
| --- | --- | --- |
| Three existing captures and two exact associated refunds | **PASS** | Fourteen official authenticated Test GETs; no gateway mutations |
| Completion, exactly-once funding/settlement and allocation arithmetic | **PASS** | All 44 checks; six balanced journals; two processed intents/transactions |
| Lender clean-return authority and independent administrator deduction | **PASS** | Persisted actors/reasons/evidence and role-negative tests; B decision explicitly simulated |
| Complete backend regression suite | **PASS** | **289 passed, 3 skipped, 0 failures**, 91.28s; fresh generated databases, credential shadowing, real gateway transport forbidden |
| Sandbox enforcement security cases | **PASS** | **100** `test_sandbox_only` cases included in full run: live-key injection, provider/path/amount/role tampering, mode conflicts and capture/payout/transfer denial |
| Webhook ingress/security cases | **PASS** | **38** `test_webhook_ingress` cases included in full run: HMAC, byte integrity, duplicate/conflict handling, body limits, stripped headers, fixed upstream and terminal-event recovery |
| Refund lifecycle, explicit approval and crash/timeout recovery | **PASS** | Finalization 13, payment regressions 36 and Razorpay/escrow 33 cases, plus provider tests; synthetic transport only |
| Complete frontend regression suite | **PASS** | **40 passed, 0 failures**, including payment and photo utilities, rerun after UI fixes |
| Browser validation-error regression | **PASS after fix** | Two actual React components, isolated headless Chrome, in-memory 422 failures; both previously unmounted, now show readable errors and clear loading |
| Production-mode frontend compilation | **PASS** | `npm run build -- --outDir <new audit artifact directory>`; **1658 modules**; running dev service preserved |
| Payment backend lint / formatting | **PASS** | Ruff check and format check across **29** payment modules, tests and scripts, after script-only cleanup |
| Frontend payment lint / formatting | **PASS** | `npm run lint:payments`, `npm run format:payments:check` on final source |
| Backend syntax / undefined names | **PASS** | Ruff `E9,F821,F822,F823` across `app`, `tests`, `scripts` |
| Full backend lint | **FAIL — existing debt** | **47** findings remain outside clean payment scope; mostly import order / unused imports, not silently waived |
| Active sandbox-only configuration | **PASS** | Test provider/key namespace, demo mode false, local exposure, test environment, auto-migrate false; live API returns sandbox flags and processed/completed status |
| Loopback/API/webhook isolation | **PASS for checked surfaces** | Ports 5175/8001/8010 bind loopback; tunnel targets only 8010; private routes return 404 through local ingress and current public origin; private API rejects public Host/forwarded headers |
| Financial read privacy and response caching | **PASS** | Anonymous 401, cross-booking 403, borrower administrator-queue 403, no-store financial responses; ordinary login was token-only and did not write records |
| Private credential files / built-secret check | **PASS for checked files/values** | All existing private-file paths return 403; no checked server-secret or fixture-password values in generated frontend assets |
| Active historical SQLite trigger protection | **FAIL** | No triggers and no payment schema-version table; launcher created tables without running payment migration; current data integrity still passes |
| Active local JWT signing key meets public policy | **FAIL** | The known repository-default key is active; local-only mode allows it. Credential preservation prohibited replacement during this audit |
| Frontend dependency audit | **FAIL at zero-advisory threshold** | Three moderate ESLint/config-array/minimatch development-tool findings; **zero high/critical**. No forced dependency rewrite |
| Backend known-vulnerable dependency pins | **FAIL** | Installed and pinned `python-multipart=0.0.12` and `python-jose=3.3.0` fall in published advisory ranges; see below |
| Complete backend dependency vulnerability audit | **NOT VERIFIED** | `pip-audit` is not installed; targeted advisory review is not a complete transitive audit |
| Real PostgreSQL behavior | **NOT VERIFIED** | Three tests skipped; no dedicated `PAYMENT_TEST_POSTGRES_URL`. Locking, migration functions/triggers and concurrency not runtime-certified on PostgreSQL |
| Independent Razorpay webhook-delivery provenance | **NOT VERIFIED** | Correlated processed receipts exist, but no independent Dashboard delivery export/session or delivery-to-event correlation was available |
| Historical explicit UI approval click | **NOT VERIFIED** | Server's strict approval input and UI gating pass tests; historical request bodies/click telemetry are not retained, so the exact click is not reconstructed |
| Public production deployment, live money and actual payouts | **NOT VERIFIED / unsupported** | No deployment/live transaction was attempted; adapter intentionally rejects live provider/capture/payout/transfer operations |
| Database/credential/service preservation | **PASS** | Before/after all-table fingerprints, original DB-file hashes where present, credential hashes and original process identities match; no migrations/restarts |

## Unresolved release findings

1. **Database hardening gap.** The active historical sandbox has valid declared check/unique constraints and clean `integrity_check` / `foreign_key_check`, but no trigger-based append-only, terminal-state or immutable-decision enforcement. `run_test_webhook_stack.py` creates tables for new stacks without installing `migrate_payments`; regression fixtures explicitly install it and therefore do not establish parity with this active database. Application/ORM checks and valid historical journals do not establish trigger enforcement. No schema mutation was made. Before demonstrating new financial mutations, prepare and validate a separately migrated disposable sandbox, with a controlled backup/migration plan for any future deployment. Do not reset or silently migrate these historical records.

2. **Signing-key provisioning.** The current local signing key is the known repository default and fails the application's public-strength guard. A caller who can reach the private API and knows that default cannot be treated as unable to mint tokens. Direct loopback restrictions and the webhook-only public tunnel limit current exposure; they do not make this a production key. Before public use, provision a strong private signing key in a separately prepared environment, review token invalidation and credentials, and rerun public-mode checks. No secret value is disclosed here and no credential was changed.

3. **Backend dependency security.** Installed `python-multipart=0.0.12` is below the patched range in the maintainer's high-severity [multipart boundary DoS advisory](https://github.com/Kludex/python-multipart/security/advisories/GHSA-59g5-xgcq-4qw3). Installed `python-jose=3.3.0` falls in the critical-rated [algorithm-confusion advisory](https://github.com/advisories/GHSA-6c5p-j8vq-pqhj). This application explicitly uses HS256 with a symmetric key; the published asymmetric/OpenSSH key-confusion precondition was not demonstrated here. Vulnerable version presence is confirmed; exploitability for every advisory is not. No exploit was sent to running services. The public ingress accepts JSON webhook bytes, not multipart upload routes. A compatible FastAPI/Starlette/auth/multipart dependency update and full transitive audit require a separate tested environment; no running package installation or broad dependency upgrade was attempted.

4. **Development dependency/style debt.** `npm audit --json` reports three moderate entries in the ESLint/minimatch chain, associated with [GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249). These are development tooling rather than compiled React runtime dependencies. Full backend lint retains 47 existing findings. Payment scope is clean. No forced major downgrade/override or repository-wide style rewrite was applied.

5. **Unverified infrastructure and provenance.** PostgreSQL behavior, complete dependency security, production authentication/rate limiting, durable evidence/backups, monitoring, retry scheduling and operational recovery are not certified by passing SQLite tests. Existing `refund.created`, `refund.processed`, `payment.captured` and `order.paid` receipts correlate with provider IDs, but a local holder of the webhook secret can also generate valid signatures. [Razorpay's validation guidance](https://razorpay.com/docs/webhooks/validate-test/) supports raw-body authentication and deduplication; it does not turn these stored receipts into independent Dashboard delivery evidence. Obtain read-only Dashboard delivery details matching the existing event IDs, destination and successful response to close that requirement. This audit did not redeliver events.

## Safe fixes and verification

The confirmed UI defect occurred when `detail` was a FastAPI array of validation objects: `PaymentModal` and `EscrowStatusCard` placed that array directly in React error state, causing the component tree to unmount. Both now use the existing `apiErrorMessage()` formatter. The browser regression used explicitly synthetic booking props, an in-memory API that throws 422, a disposable Chrome profile and blocked financial network routes. Before the fix both cards unmounted; after it both remained mounted, displayed `booking_id: Synthetic invalid booking`, and cleared loading. No provider/business-state transition or authorization rule changed.

Import order and formatting were corrected only in `backend/scripts/create_payment_demo.py`; list formatting was corrected in `backend/scripts/verify_payments.py`. The affected demo test passed **1/1** afterward, and all 29 payment files passed lint/format checks. The full backend run preceded these semantically neutral script corrections; the relevant script test was rerun. The complete frontend suite, lint, formatting and build passed on the final UI source. No historical data repair or financial logic change was made.

The initial private-file probe incorrectly treated the nonexistent shared root `.env` as an existing credential file: Vite returned an HTML SPA fallback with 200. The corrected probe checks files that actually exist; backend `.env` and both private account files return 403. This was an audit false negative, not a confirmed secret leak. The original result and correcting supplemental evidence are both retained.

## Preservation and exact next action

The active database was opened with SQLite `mode=ro` and `query_only=ON` for audit queries. All historical table fingerprints remained identical through provider reads, runtime reads, tests and fixes. Existing credential files and original database files where present remained identical. Backend, ingress, controller, frontend and existing tunnel process identities were preserved. Regression writes were confined to newly generated test databases. The only application POST during live verification was ordinary existing-user login, whose implementation issues a token without committing database changes. All real financial gateway requests were GETs. Browser regression actions were in memory; no real financial endpoint was called.

Only the two UI error handlers, two verification-script style issues and documentation were changed, with audit artifacts added. No financial record, payment/refund/deduction, service configuration, credential, live package installation or EP integration was changed. No Git commit, branch or push was made.

For the academic demonstration, sign in using the existing private fixture credentials, open A and B, and click **Refresh payment status**. Show **Processed — confirmed settlement**, the allocation and balanced journal. Keep the original ₹1 booking unchanged. No refund, retry, reconciliation, claim approval or clean-return action remains for these completed scenarios. Present the failures and NOT VERIFIED items explicitly. Further financial mutation demonstrations require a separately prepared sandbox with the missing hardening addressed; production release remains blocked.

## Reproduction and evidence

Private ignored evidence directory: `backend/.payment-verification/finalization-20261111/final-release-20261111/`. No credential values are embedded in these reports.

| Artifact | Purpose |
| --- | --- |
| `release-readiness.json` | Final machine-readable PASS / FAIL / NOT VERIFIED decision, check counts and preservation results |
| `provider-and-runtime.json` | Fresh provider GETs, 44 financial assertions, local booking/authorization/journal records, live read checks and schema inspection |
| `backend.xml`, `backend.log`, `backend.json` | Full backend tests, skip reasons, exact command and times |
| `backend-affected.*` | Post-cleanup demo-script regression |
| `frontend-tests.*`, `frontend-lint.*`, `frontend-format.*`, `frontend-build.*` | Final frontend results and exact commands; build output in `frontend-dist/` |
| `backend-payment-lint.*`, `backend-payment-format.*`, `backend-all-lint.*`, `backend-integration-errors.*` | Exact lint scope, successful payment checks and unresolved legacy findings |
| `ui-error-regression-before.json`, `ui-error-regression-after.json` | Browser reproduction and correction using synthetic actions only |
| `frontend-dependency-audit.*`, `backend-dependency-audit.json`, `security-supplement.json` | Advisory counts, installed versions, scope limits, private-file/build-secret and tunnel checks |
| `baseline.json`, `preservation.json` | All-table / credential / original-file / existing-process preservation and the two intentional frontend source changes |

The audit runner and read-only provider/browser/security scripts are retained one directory above these artifacts. From `backend/`, `final_release_checks.py backend` uses fresh generated databases; for a later independent run choose fresh artifact/temp paths first. Do not reuse the old unpaid-fixture runtime/browser/preparation scripts against completed scenarios: their assertions reflect preparation state, and the preparation command can create orders. Direct provider audit code is GET-only; application reconciliation is deliberately excluded.
