# Refund correction and verification — 14 November 2026

The user approved local correction after the read-only incident investigation, and requested that actual lender transfer support also be scoped. The approved correction is implemented and validated. No real order/payment/refund/transfer, hosted write, migration, secret change, checkpoint change or Git history/remote operation was performed. Prior unrelated local stabilization changes were preserved.

**Activation status:** activated after explicit user approval to restart the existing backend and verify with GETs. The original port-8000 backend (PID 8732) was replaced by PID 17872; the existing Vite process (PID 6464) was preserved. Direct and Vite-proxied database-backed health checks return 200, and the new routes are loaded. Existing database records and the incident's unsupported ₹180 allocation have not been repaired or relabeled as paid. The separate transfer design is scoped, not enabled.

## Resulting behavior

- A clean return still authorizes only deposit minus approved damage deduction. For the exact drill case: capture ₹580, authorized deposit refund ₹400, recorded rental allocation ₹180. No rental-fee refund or lender payout is introduced.
- New read-only `GET /api/payments/bookings/{booking_id}/gateway-reconciliation` uses actual provider GETs for the captured payment and bounded refund inventory. It checks ownership/admin authorization, order/payment association, integer-paise amount, currency, statuses, duplicate IDs, authorization matching and aggregate totals. Incomplete inventory or provider failure is unavailable, never healthy reconciliation.
- The rental page checks this endpoint during its normal payment refresh, including completed rentals. It displays excess/unmatched refunds and distinguishes historical capture, local deposit settlement, recorded rental allocation and current gateway refund coverage. It never describes an allocation as a completed lender payout.
- Before a new refund dispatch, the backend verifies provider inventory and remaining gross principal. Unverified/mismatched evidence stops dispatch. A previously accepted request with the current immutable receipt is recovered by GET, without another POST. Admin approval, amount constraints, leases and immutable terms remain enforced.
- New admin-only `POST /api/payments/refunds/inspect` performs provider GETs and records a verified discrepancy as an append-only financial audit/review event. It does not change settlement amounts, create refund intents, send money, or reverse journals. Existing admin reconcile also checks completed refunds rather than returning stale saved status alone.
- Verified external refund webhooks are linked through the authoritative original captured payment and full refund inventory. Unknown receipts do not grant settlement authority. A mismatch creates a deduplicated admin review/audit/notification; replay does not create another case or refund. Creation receipts remain informational when no local captured payment exists to reconcile, and known creation is not proof of settlement.
- Completed rentals with recorded gateway discrepancies appear in the protected admin queue. Dispatch/retry controls remain blocked for recorded review. Review flags do not automatically clear or authorize accounting reversals.

The provider adapter's payment/refund allowlist and Test Mode policy remain intact; only a bounded GET inventory helper was added. Ledger posting rules, models, schema, migrations, private-key settings and the original funding/settlement journals are unchanged.

## Files changed for this correction

Backend:

```text
backend/app/services/gateway_reconciliation.py                 new
backend/app/services/razorpay_service.py
backend/app/services/payments.py
backend/app/routers/payments.py
backend/app/routers/disputes.py
backend/tests/test_gateway_refund_reconciliation.py            new
backend/tests/test_razorpay_escrow.py
```

Frontend:

```text
frontend/src/components/GatewayRefundStatus.jsx                new
frontend/src/components/EscrowStatusCard.jsx
frontend/src/components/RefundPanel.jsx
frontend/src/components/PaymentReviewQueue.jsx
frontend/src/components/paymentFlow.js
frontend/src/components/integration.test.js
frontend/package.json                                         scoped lint includes new component
```

Documentation:

```text
docs/razorpay-refund-incident-20261114.md                        forensic baseline
docs/razorpay-refund-correction-20261114.md                      this report
docs/lender-transfer-scope-20261114.md                          requested transfer design
```

Additional collectors, isolated harnesses, XML, browser results and builds are confined to ignored `backend/.payment-verification/refund-incident-20261114/`. Changes predating this correction are listed separately in `docs/integration-stabilization-20261114.md`.

## Verification

| Check | Result |
| --- | --- |
| Initial forensic characterization, before fixes | 15 passed; reproduced completed-refund visibility and unknown-webhook gaps. Synthetic transport/generated SQLite only. |
| Initial targeted correction tests | 50 passed. |
| Final focused refund/authorization/webhook/reconciliation tests | 59 passed. |
| Final full backend suite | **524 passed, 23 skipped**, zero failures. PostgreSQL-only cases skipped because no dedicated disposable PostgreSQL URL was supplied. |
| Frontend `npm test` | **78 passed**, zero failures. |
| `npm run lint:payments` | Passed, including the new gateway status component. |
| Scoped backend Ruff | Passed. |
| Vite build | Passed, 1,685 modules; output in the ignored incident folder, existing frontend/dist preserved. |
| Mounted Chrome, real React/FastAPI, synthetic provider/isolated SQLite | **10 checks passed**, zero unhandled browser exceptions; all child test processes and isolated server stopped. |
| New inspector against real configured incident | **Review required**: ₹400 authorized, ₹580 processed refunds, ₹180 unmatched, ₹0 gross principal retained. Two provider GETs only. No running-app restart or hosted write. |
| Approved activation and actual HTTP GETs | Replacement backend healthy on port 8000; Vite proxy healthy on port 5173. Authorized borrower GET through Vite reports **review_required**, ₹400 authorized, ₹580 refunded, ₹0 remaining; unauthenticated inspection returns 401. Existing rental payment GET returns 200; admin queue GET returns 200 for the verified independent admin and 403 for the borrower. No login/payment/review POSTs were sent. |
| Preservation | All 20 hosted application-table fingerprints still match the incident baseline; backend `.env` and actual checkpoint hashes unchanged. `git diff --check` passed. |

The first broad correction run reported 518 passed, 2 failed, 23 skipped: the failures exposed loss of informational refund.created behavior with no captured application payment. That compatibility was restored without weakening funded-rental inspection. Final full-suite results above include that correction and the expanded regression cases. The earlier isolated harness initially blocked Windows asyncio's internal socketpair; the corrected harness permits only that internal operation while blocking all application network connections.

New regression coverage includes exact drill amounts, completed-settlement mismatch, read-only GET preservation, admin-only review, no duplicate audit under concurrent review, malformed/incomplete provider data, authorization denial, unavailable gateway, wrong currency, lost POST receipt recovery in pending/processed/failed states, external creation/processed webhook replay, and unchanged balanced journals. Existing cancellation, failed-refund recovery and concurrency/immutability regressions pass too.

Mounted browser checks verify healthy refund inventory, explicit simulated-allocation wording, failed-check visibility/recovery, extra-rent refund detection after completion, borrower/admin separation, completed-case visibility, absence of retry controls, exactly one original synthetic deposit refund POST, and zero unhandled exceptions.

## Reproduce safely

From `backend/`, the isolated runner clears hosted configuration inside its process, generates its own SQLite/JWT via conftest, denies application socket connections and uses synthetic gateway transport:

```powershell
& 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe' -B .payment-verification/refund-incident-20261114/run_fix_tests.py recheck tests
```

Use a fresh run label each time to preserve previous test artifacts. The mounted isolated browser check is:

```powershell
& 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe' -B .payment-verification/refund-incident-20261114/browser_fix.py
```

Frontend checks from `frontend/`:

```powershell
npm test
npm run lint:payments
npm run build -- --outDir ../backend/.payment-verification/refund-incident-20261114/frontend-dist-recheck
```

The real incident was inspected through the new pure read-only service from a separate process; the hosted `/refunds/inspect` or `/refunds/reconcile` POSTs were **not** invoked. Those routes can record review evidence and must not be confused with read-only GET inspection.

## Remaining limits and operational steps

1. The verified code is now loaded in the single replacement backend instance at `http://127.0.0.1:8000`. The existing frontend remains at `http://127.0.0.1:5173`; a normal rental-page refresh can display the real incident discrepancy using GETs alone. Activation used the configured PostgreSQL and Razorpay Test provider with `AUTO_MIGRATE=false`. All 20 hosted table fingerprints, environment files and checkpoint hashes still match the investigation baseline after startup and GET checks. Historical process metadata and logs were preserved; replacement process metadata is in `activation.json`.
2. The ₹180 refund initiator remains unknown. Application code cannot prevent a person or another service with gateway permissions from issuing direct refunds outside NeighborLend. Restrict those access paths and establish provider-side attribution before deciding how to reconcile the historical discrepancy.
3. Existing incident accounting correction needs a separately approved, attributable compensating journal or funding decision. Do not rewrite the capture, processed ₹400 refund, immutable terms or old journals; do not send another refund or charge the borrower again automatically. Review flags intentionally require such an explicit resolution rather than a blind “clear warning” action.
4. Production webhook ingress/delivery is not verified; the current server is loopback-only and the hosted receipt table was empty at investigation time. The UI's fresh read-only inspection detects the mismatch without relying on webhook delivery. Recording it into the persistent admin queue requires explicit admin inspection, a blocked dispatch that detects it, or a verified delivered webhook.
5. Actual lender transfers remain **scoped only**. Route entitlement/API behavior, onboarded lender destinations, fees/net-payable policy, additive schema and explicit Test transfer approval are outstanding. The incident payment is fully refunded and cannot be treated as available ₹180 funding. See `docs/lender-transfer-scope-20261114.md`.
6. The checks are point-in-time evidence. A concurrent external dashboard/API refund can occur after a snapshot; this patch detects discrepancies and stops unsafe application retries but does not claim global control of Razorpay or regulated escrow. No payout, transfer, reversal, provider refund or hosted adjustment was executed to “repair” the incident.

Key artifacts: `full-final.xml`, `focused-final.xml`, `fixed-real-readonly.json`, `activation.json`, `activated-backend.log`, `route-readonly.json`, `frontend-dist/`, and the generated `browser-*/results.json` / `cleanup.json`.
