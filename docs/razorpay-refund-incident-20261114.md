# Electric drill refund investigation — 14 November 2026

## Executive finding

The intended clean-return refund was **₹400**, and NeighborLend authorized and dispatched exactly that amount. A separate **₹180 refund** exists against the **same original ₹580 payment**. Both refunds were `processed` when read from Razorpay during **14:56:39–14:56:54 IST**; the payment reports `amount_refunded=58000`, `refund_status=full`, and `status=refunded`.

**The precise caller/reason for the ₹180 refund remains unverified.** There is no matching application refund intent, attempt, payment transaction, audit record, or webhook receipt anywhere in the inspected financial tables. Its `receipt` is null and its only note is an empty `comment`. This differs from the current backend's required amount/speed/receipt dispatch contract. Evidence strongly supports an out-of-band gateway refund; it does not establish a particular dashboard user, API client, automation, or provider action. The user clarified that ₹180 was intended as rent paid to the lender; this is business intent, not evidence identifying who created the refund.

There is a **confirmed reconciliation/visibility defect**: the application continues to show a completed clean return and ₹180 simulated lender earnings after the gateway has refunded all ₹580. Existing double-entry journals remain balanced, but the ₹180 receivable is no longer backed by the gross unrefunded payment balance.

The ₹180 entity is a **refund linked to the original borrower payment**. Current NeighborLend code implements simulated lender accounting and explicitly excludes transfer/payout operations. It cannot identify this refund as a lender payout. Razorpay documents normal refunds as returning to the original payment method: [normal refund documentation](https://razorpay.com/docs/payments/refunds/normal/). No real bank credit or debit is established by these Test Mode records.

This report records the read-only investigation baseline. The user subsequently approved local corrections and requested that actual lender transfer/payout support also be scoped. No hosted transaction correction, migration, refund, or transfer is authorized or executed by this report.

## Verified identifiers, redacted

Aliases are stable, truncated SHA-256 hashes of complete identifiers, not partial original identifiers. Equality below represents exact identifier equality checked privately.

| Record | Redacted alias |
| --- | --- |
| Drill listing | `redacted-d36b58a0c25a` |
| Accepted offer | `redacted-28287d5805fa` |
| Listing conversation | `redacted-5aacaf89b65f` |
| Borrow request | `redacted-9e1f0ef438d7` |
| Booking | `redacted-78268a510eac` |
| Gateway order | `redacted-144abc091eed` |
| Captured gateway payment | `redacted-637b93ffb580` |
| Application refund intent | `redacted-f1dcf901c166` |
| ₹400 gateway refund | `redacted-9e713b5051cc` |
| ₹180 gateway refund | `redacted-fada510863d2` |

Exactly one booking matches ₹180 rent + ₹400 deposit = ₹580. Its listing name matches drill. Booking→offer/request/listing, order→payment, and both refund→payment relationships were verified by IDs and amounts, not timestamps alone. Both provider order and payment are INR 58000 paise and match the stored order/payment IDs.

## Timeline

All times are **14 November 2026, IST (UTC+05:30)**. Database naive timestamps are interpreted as UTC because the application writes `datetime.utcnow()`. Gateway timestamps are Unix seconds. Their clocks/precision differ; the order timestamp is slightly earlier than local consent recording, so cross-system second ordering alone is not causal evidence.

| Time IST | Source | Verified event |
| --- | --- | --- |
| 14:39:21.948 | DB offer | Borrower offer created at ₹180/day with ₹400 deposit. |
| 14:39:42.533–14:39:43.238 | DB request/offer/booking/audit | Offer accepted; request and immutable booking snapshot created. Snapshot audit actor is lender. The offer's last update is 14:39:42.853; a distinct accepted-at column is unavailable. |
| 14:40:57 | Razorpay order | ₹580 order created; its receipt matches the application order-operation record. |
| 14:40:58.511–14:40:59.646 | DB audit | Borrower checkout terms accepted; order becomes ready. |
| 14:41:27 | Razorpay payment | Payment entity created. A separate authorization/capture timestamp is not supplied by this fetched entity. |
| 14:41:46.363–14:41:46.987 | DB journal/payment/audit | ₹580 captured payment and balanced funding journal persisted; actor borrower. The exact HTTP verification entry point/signature invocation cannot be distinguished from payment reconciliation using the available audit/log evidence. |
| 14:42:53.471–14:43:32.296 | DB audit | Lender uploads three handover evidence records. |
| 14:44:52.849 | DB request | Borrower receipt confirmed. |
| 14:45:29.439 | DB request | Lender completes handover; rental starts. |
| 14:46:11.064–14:46:12.029 | DB audit/request | Borrower return evidence uploaded; return reported. |
| 14:46:43.407–14:46:43.770 | DB request/intent/audit | Lender approves clean return and authorizes ₹400 refund with zero deduction. No dispute, rejection, or cancellation record. |
| 14:48:34.610–14:48:34.892 | DB attempt/audit | Independent admin requests the authorized refund. |
| 14:48:34 | Razorpay refund | ₹400 refund created; receipt exactly matches the intent idempotency key. |
| 14:48:37.610 | DB audit | Gateway refund recorded as pending. |
| 14:48:55.354–14:48:55.622 | DB attempt/audit | Same admin requests a status check of the same ₹400 refund. This is a second local attempt record, not evidence of a second refund POST. |
| 14:48:58.165–14:48:59.239 | DB audit/journal | ₹400 refund confirmed processed; settlement journal posted; booking completed, request closed, deposit settled. |
| 14:50:57 | Razorpay refund | Distinct ₹180 refund created against the same payment; no matching application record. Exact processing completion time is unavailable. |
| 14:56:39–14:56:54 | Investigation GET/SELECT snapshot | Both gateway refunds processed; ₹580 fully refunded. DB still records only ₹400 refunded and ₹180 lender allocation. |

**Webhook evidence:** `processed_webhooks` contains zero rows, including no target payment/refund receipts. No webhook was replayed or sent.

**Application-log evidence:** the existing healthy backend returned 200 and was not restarted. Its 577-byte startup log has zero access-request lines and no relevant payment/refund IDs; the original launcher disables access logging. Logs therefore cannot identify the caller of the extra refund. Absence of log lines is not proof that a particular request never happened.

## Gateway versus database reconciliation

| Measure | Database / simulated ledger | Razorpay Test API |
| --- | --- | --- |
| Original capture | ₹580 captured | ₹580, captured flag true; current status refunded |
| Deposit allocation | ₹400 | Gateway has no application deposit sub-account |
| Authorized clean-return refund | ₹400, processed, one intent | Same ₹400 refund, processed, matching ID/receipt |
| Additional rental-fee refund | No record | Separate ₹180 refund, processed, null receipt |
| Total refunds | ₹400 | ₹580 |
| Gross retained value | ₹180 gateway-clearing debit / lender-receivable credit | ₹0 unrefunded principal |
| Physical/booking state | return confirmed / completed / settled | Order remains paid; payment fully refunded |

The original capture is historical fact; a `captured` database field need not be overwritten merely because the provider's current payment status is `refunded`. Historical capture and current refund coverage need distinct presentation. Provider fees/taxes are outside this gross simulated-ledger comparison and are not evidence of a lender payout.

The two posted journals are internally correct for the application-authorized ₹400 refund:

| Journal | Debit | Credit |
| --- | --- | --- |
| Funding | gateway_clearing ₹580 | rental_fee_clearing ₹180; escrow_deposit_held ₹400 |
| Settlement | escrow_deposit_held ₹400; rental_fee_clearing ₹180 | gateway_clearing ₹400; lender_receivable_simulated ₹180 |

Each journal has ₹580 debit and ₹580 credit; all lines match their headers. The ₹180 debit to rental_fee_clearing transfers the earning allocation into lender_receivable_simulated; it is not a second gateway refund. No subsequent reversal journal exists. Deposit liability is zero and refunded deposit is correctly ₹400. There is a ₹180 difference between ledger backing and the gateway's current gross refundable-payment position.

## Origin analysis and exact code paths

| Candidate cause | Evidence and finding |
| --- | --- |
| Successful return automatically refunds rent | Not supported. `backend/app/services/payments.py:706` `_intent` uses deposit minus deduction for clean returns; `:869` `return_decision` authorizes that intent only. This incident's saved amount is 40000, kind clean_return. |
| Intentional application cancellation/full refund | Not supported. `payments.py:749` permits cancellation only before receipt/activation; cancellation adds rental fee to the deposit. The incident has no cancellation authorization and a completed active/returned rental. A normal full cancellation here would authorize ₹580, not a standalone ₹180 refund. |
| Admin dispatch | Proven for ₹400 only: `backend/app/routers/payments.py:328`, `payments.py:1091`. Actual DB admin actor, approval flag, immutable amount, and saved key govern dispatch. The extra ₹180 has no matching application action. |
| Frontend amount bug | No demonstrated path. `frontend/src/components/RefundPanel.jsx:37` sends booking/approval, not an amount or destination. `:67` labels retained rent; `:133` requires an explicit amount-labelled approval checkbox. `ReturnInspection.jsx:15` sends only a return decision. |
| Automatic retry/duplicate | No evidence. Two attempt rows share the exact ₹400 refund ID/key; the second is audited as a status check. `payments.py:1162` fetches an existing refund; `:1315` permits a new failed attempt only after admin authorization and authoritative terminal failure. The ₹180 is a distinct refund with no key. |
| Webhook/reconciliation created it | No recorded webhook delivery. `reconcile_refund` calls `execute_refund(...allow_dispatch=False)` at `payments.py:1312`, which uses GET recovery rather than a new POST. |
| Lender payment | Current provider allowlist excludes payout/transfer/account/settlement APIs (`backend/app/services/razorpay_service.py:224`). `payments.py:278` explicitly exposes simulated lender allocation and `provider_transfer_verified=False`. A refund against the original payment does not identify a lender recipient. |
| Dashboard, another API client, provider action, or another deployment | Consistent with missing application records and null receipt/empty comment. **Not attributable to a precise actor/client from the available evidence.** No caller/source/initiator field is returned by the fetched refund entity. Dashboard audit history or provider-side request attribution is needed. |

Razorpay defines `receipt` as a merchant reference, not an authenticated identity of the caller, and documents pending/processed/failed refund states: [refund entity](https://razorpay.com/docs/api/refunds/entity/). A null receipt supports the mismatch with this application's dispatch contract; it does not prove dashboard origin.

## Confirmed defect and protections

**HIGH before live use: completed-settlement external-refund visibility gap.**

- `backend/app/services/payments.py:218` `view` computes only local deposit reconciliation; `:280` reports rent from the booking snapshot. `:398` `get` reads saved state. A balanced deposit ledger is not whole-payment gateway reconciliation.
- `execute_refund` returns immediately for a processed intent (`payments.py:1107`), so even the existing reconcile path does not inventory later gateway refunds.
- `frontend/src/components/paymentFlow.js:231` hides payment reconciliation after capture and refund operations after processed settlement. `EscrowStatusCard.jsx:79` continues to display the saved lender earning as payable.
- `backend/app/routers/payments.py:435` acknowledges refund.created without review; `:442–471` cannot bind a processed external refund with a null/nonmatching receipt and returns 503. `backend/app/routers/disputes.py:15–43` excludes this completed, locally processed booking from the admin queue. The webhook gap is reproduced locally but did not demonstrably cause this incident because the hosted webhook table is empty.

The following protections are present in the hosted catalog and code; none was weakened or executed destructively:

- Unique refund intent per booking; unique operation/idempotency keys and gateway refund IDs; immutable refund allocation terms.
- Enabled `nl_refund_allocation_guard` requires clean-return/dispute refund plus deduction to equal the deposit; cancellation must equal the full total.
- Enabled `nl_payment_binding_guard` binds transaction amounts and refunds to authorized bookings/intents. Immutable capture/processed states and append-only ledger/audit triggers remain enabled.
- Booking row locks, dispatch lease/active-attempt checks, same-key provider requests and unique journal references prevent application races/replays. The provider uses `X-Refund-Idempotency`; this is the documented normal-refund mechanism: [Razorpay idempotent refunds](https://github.com/razorpay/markdown-docs/blob/master/api/refunds/normal-refunds-idempotent.md).

These application/database controls do not govern a separate caller using Razorpay directly. The observed sum is exactly ₹580, not more than the original payment; it is **₹180 over the business-authorized clean-return refund**, not a proven duplicate ₹400 refund or an above-capture refund.

**Financial impact:** Test Mode shows ₹180 of unsupported simulated lender receivable; no live-money loss or lender bank payout is established. The same undetected divergence would be financially significant if reused in a live system. Actual lender payout support is a separate missing integration, not something to implement by refunding rental fees.

## Minimal correction and transaction-reconciliation requirements

The user has now approved local corrective work. Preserve capture history, the legitimate ₹400 processed intent, immutable booking terms, and posted journals.

1. Add authoritative GET-only payment/refund inspection, including completed bookings. Verify payment/order/currency/amount, inventory all refunds with bounded pagination, and compare total/provider refund IDs with authorized intent/attempt records. Distinguish unknown, pending, processed and mismatched external refunds. Provider failures must not be shown as healthy reconciliation.
2. Before a new gateway refund dispatch, check for extra/existing provider refunds and remaining refundable balance; never silently generate a new key or duplicate POST after an unknown outcome. Keep explicit admin approval and the clean-return deposit-only bound.
3. Bind unknown refund webhooks to the original stored payment, verify provider evidence with GETs, and flag external/unmatched refunds for admin review. Do not treat webhook notes, null receipts or observed money movement as new settlement authority.
4. Show current gateway reconciliation separately from historical capture and deposit-ledger balance. Allow admin status checks on completed rentals. Explain when rent is a simulated ledger allocation and when a discrepancy means it cannot be described as backed/available for payout.
5. For this existing ₹180 discrepancy, first establish provider-side attribution and the intended business decision. If an accounting reversal is approved, append an idempotent compensating journal, for example Dr lender_receivable_simulated ₹180 / Cr gateway_clearing ₹180, plus attributable audit evidence. Do not rewrite old journals, reclassify the original ₹400 intent as cancellation, force captured→refunded into the historical capture field, or issue another refund. Any reimbursement/payout alternative requires a separate approved flow.
6. Scope actual lender transfers separately: proper provider product/capability, onboarded lender destination, server-authorized net payable, fees/payout policy, idempotency and transfer reconciliation. Never use `/payments/.../refund` to pay a lender. No provider capability setup, transfer, hosted migration, or financial correction was performed by this investigation.

## Tests and regression plan

Read-only real-service evidence is separate from isolated tests. **15 isolated tests passed**: existing admin-only refund/approval/pending processing/cancellation/recovery/concurrency/immutability cases, plus three forensic characterizations. Those three reproduce (not endorse) current stale completed-refund reads, unmatched processed-webhook 503 without an admin queue case, and ignored external refund.created.

All application socket connections were denied. Only Windows asyncio's internal loopback socketpair was permitted; generated SQLite databases and synthetic Razorpay transport were used. The first run had 15 setup errors because the guard also blocked that Windows internal socketpair; no application defect was inferred from those errors. The corrected harness passed all 15 without application changes.

Before closing the approved correction, add regression expectations for exact ₹580/₹400/₹180 funding and settlement; completed-booking extra-refund detection; pending/failed external refunds; malformed/mismatched payment IDs, amounts and currencies; pagination incompleteness; provider timeouts; no POST during reads/reconciliation/webhooks; duplicate/out-of-order events; dispatch/retry races; explicit admin authorization; stale UI/session changes; and lender transfer isolation from refunds. Existing processed settlement should remain immutable through every case.

Evidence under `backend/.payment-verification/refund-incident-20261114/`:

- `collect.py`, `evidence.json`: real SELECT/GET evidence and redacted correlations.
- `extra_checks.py`, `extra-evidence.json`: global extra-refund absence checks, enabled guard definitions and log limitations.
- `before-fingerprints.json`, `after-fingerprints.json`: all 20 application tables unchanged during collection.
- `test_characterization.py`, `run_isolated.py`, `isolated-tests-final.xml`: isolated forensic reproductions/regression results; initial errors retained in `isolated-tests.xml`.

## What remains unverified

The ₹180 initiating actor/client/reason; the exact capture authorization and HTTP verification route; actual webhook configuration/delivery or rejected requests not durably recorded; provider dashboard request/audit history; lender bank receipt; real-money movement; actual lender-transfer product access/onboarding; and behavior of live write paths under PostgreSQL contention. No new backend was started, no secrets or checkpoint were changed, no hosted data/migration/webhook replay/payment/refund/cancellation/transfer was executed, and no Git history or remote operation was performed during the investigation.
