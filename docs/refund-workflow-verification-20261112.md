# Refund workflow verification — 12 November 2026

Rental request: `38af43ff-454f-4413-beda-6f84c9a4034f`.

The existing ₹3,400 refund is **authorized but unsent**. This is not a verified Razorpay failure. The hosted rental has never entered refund dispatch: no refund attempt, provider refund identifier, `refund_requested` audit event, or gateway refund exists. Clean-return confirmation intentionally creates an authorization; sending a Razorpay Test refund requires a separate explicit approval. That approval remains outstanding under the debugging instructions.

## Verified hosted state

The configured PostgreSQL/Supabase target was checked against the intended project without publishing connection details. Inspection used a PostgreSQL `READ ONLY` transaction and an enforced GET-only Razorpay provider wrapper. No financial mutation endpoint was called.

| Check | Independently observed result |
| --- | --- |
| Borrower / actual lender | `aarav_mehta` / `priya_sharma` |
| Rental request / physical return | `fulfilled` / `return_confirmed` |
| Return evidence | Four saved return-photo references; borrower return reported and lender return confirmed |
| Financial booking | `settling`; payment `captured`; deposit `refund_pending` |
| Settlement authorization | One `clean_return` intent, status `created`, authorized by Priya as this rental's lender |
| Authorized refund / deduction | ₹3,400 / ₹0 |
| Rental fee retained | ₹500; lender accounting remains simulated, with no payout |
| Refund attempts | None |
| Intent error / provider refund reference | None / absent |
| Dispute | None |
| Ledger | One posted journal, balanced debits/credits; ₹3,400 remaining liability, reserved for the existing intent |
| Financial transactions | One ₹3,900 order (`ready`), one ₹3,900 payment (`captured`), no refund transaction |
| Razorpay payment GET | Captured, ₹3,900 INR, ₹0 refunded |
| Razorpay refund-list GET | Complete paginated inventory; zero refunds |

The ₹0 **unreserved** balance is expected: the existing authorization reserves the full ₹3,400 deposit. It is not evidence that the deposit was refunded or that a new refund intent should be created. Gateway unrefunded capture is ₹3,900; clean-return eligibility remains limited to the ₹3,400 deposit.

Port 8000 was tested with existing private credentials, which were never printed. Only authentication POSTs and financial/document GETs were issued:

| Account | Login / identity | Rental read | Payment receipt | Refund acknowledgment |
| --- | --- | --- | --- | --- |
| `aarav_mehta` | 200 / correct non-admin | 200 | 200 | 409: not yet eligible |
| `rohan_kapoor` | 200 / correct non-admin | 403: unrelated to this rental | Not requested | Not requested |
| `priya_sharma` | 200 / correct admin and actual lender | 200 | 200 | 409: not yet eligible |

The acknowledgment must remain unavailable until a verified processed refund. Hosted table count/digest comparisons before debugging and after the local authentication/read checks matched, including users, rental, payment, refund, journal, ledger, dispute and notification tables.

## Trace and defects repaired

1. The lender's return control sends `POST /api/borrow-requests/{id}/return/confirm` with `approved` and the condition note. Backend ownership, captured-payment, return evidence and return-state checks authorize the clean-return intent atomically. The Razorpay branch deliberately does not execute a refund here. The existing rental completed this transition successfully.
2. `RefundPanel` dispatches through `EscrowStatusCard` to `POST /api/payments/refunds/execute` with the existing `booking_id` and strict boolean `gateway_refund_approved`. The endpoint and payload match the backend. No current JWT mismatch was found. Unrelated users remain forbidden; failed gateway refunds still require an administrator's separately approved retry.
3. **Reproduced defect:** the UI enabled `POST /api/payments/refunds/reconcile` for a newly created, unsent intent. The backend created a dispatch attempt before discovering that the gateway refund did not exist, returning 503 `refund_reconciliation_required` and changing the intent to `unknown`. A fresh isolated test reproduced this before the fix. Reconciliation now preserves an unsent authorization without a provider call or invented attempt. The UI disables premature reconciliation and explains the separate dispatch approval.
4. **Refresh defect:** an action error previously skipped the immediate booking/rental refresh. A lost response could therefore leave a stale displayed outcome. Both authoritative reads now run after either POST result, with no automatic POST retry. Refresh errors stay visible. Neither a response body nor an exception is treated as proof of financial success. Refund consent also resets when the saved intent status changes.
5. **Session defect:** `localStorage.nl_token` is shared between tabs in a browser profile, while the displayed React user previously stayed unchanged in other tabs. Axios could therefore send another account's current token from stale account UI. An external login/logout now clears displayed identity and reloads account-scoped state. Authentication errors no longer log the complete Axios error object, which may contain request headers.

The new diagnostics verify current state and reproduce the integration defect; they do not establish which button produced the user's historical browser error. No historical browser console capture or backend stdout file was available. The financial audit contains no refund dispatch/error event for this rental. The isolated browser run had zero uncaught exceptions.

## Local changes in this task

| File | Change |
| --- | --- |
| `backend/app/services/payments.py` | Preserve unsent authorization during reconciliation |
| `backend/tests/test_refund_workflow_debugging.py` | Isolated regression for unsent reconciliation, approval and ownership |
| `backend/tests/test_payment_finalization.py` | Update old assertion expecting the premature-reconciliation 503; keep explicit approval and single-dispatch assertions |
| `backend/scripts/inspect_refund.py` | READ ONLY database / GET-only gateway inspection and optional port-8000 authentication/read checks |
| `backend/scripts/verify_refund_browser.py` | Disposable browser verification using synthetic APIs with hosted/provider URLs blocked |
| `frontend/src/components/RefundPanel.jsx` | Clear authorization state, separate dispatch instructions and disabled premature reconciliation |
| `frontend/src/components/EscrowStatusCard.jsx` | Refresh saved financial/rental state after action errors; reset consent on status change |
| `frontend/src/components/paymentFlow.js` | Shared action/refresh helper that never retries a financial POST |
| `frontend/src/components/payments.test.js` | Lost-response, refresh-error, consent and tab-session regressions |
| `frontend/src/context/sessionSync.js` | Observe cross-tab authentication changes |
| `frontend/src/context/AuthContext.jsx` | Invalidate/reload stale account UI; suppress sensitive error objects |
| `docs/refund-workflow-verification-20261112.md` | This report |

No design, CSS, database schema, JWT configuration, AI pipeline, allocation formula or journal posting rules were changed in this task. Existing uncommitted work was preserved.

## Test report

All automated gateway operations used synthetic transports; all backend fixtures used generated SQLite databases or UUID schemas in a dedicated loopback PostgreSQL test database. No automated test issued a network refund request.

| Verification | Result |
| --- | --- |
| New regression before fix | One expected failure: unsent reconciliation returned 503; ownership/approval test passed |
| New regressions after fix | 2 passed |
| Full backend `python -B scripts/verify_payments.py` | 437 passed, zero skipped, including dedicated local PostgreSQL cases |
| Frontend `npm test` | 50 passed |
| Real headless Chrome refund interaction checks | 7 passed |
| Existing upstream frontend browser regressions | 13 passed, including styling comparison, login, private evidence, both handover confirmations, return, AI response reuse and access gates |
| Frontend production build | Passed |
| Payment ESLint / context-file lint | Passed |
| Payment Prettier check and changed context-file format check | Passed |
| `git diff --check` | Passed; existing Windows line-ending notices only |

The first full run had 436 passing tests and one assertion that explicitly expected the old 503 behavior. That assertion now checks preserved `created` state and zero provider calls; explicit dispatch approval and single-POST checks remain intact. The complete rerun passed all 437 tests in 264.78 seconds.

The backend suite covers clean-return eligibility, both-party return/evidence gates, unverified capture rejection, duplicate prevention, pending/failed/unknown reconciliation, provider errors and mismatched responses, refund intent lifecycle, full/partial/zero allocations, independent administrator dispute review, balanced journals, authorization, authenticated documents, JWT/authentication and existing rental/payment/dispute regressions. Real browser checks exercise borrower and lender approval, exact API payload, pending-to-processed reconciliation, UI refresh, a lost response without repeat dispatch, failed-refund admin consent, outsider controls, and both document downloads.

Idempotency remains the existing immutable refund key and exact payload, with `X-Refund-Idempotency`; the provider adapter was not changed. This matches [Razorpay's official idempotent refund documentation](https://github.com/razorpay/markdown-docs/blob/master/api/refunds/normal-refunds-idempotent.md). Reconciliation of a previously dispatched refund continues to use provider GETs.

Local artifacts: `backend/.payment-verification/refund-debug-20261112/browser-checks.json` and `backend/.payment-verification/refund-debug-20261112/backend.xml`. The hosted diagnostic reports and table fingerprints are kept inside the existing developer-only, Git-ignored private test-data directory. They contain no passwords, JWTs or database connection secrets.

## Session testing and next action

Use three separate browser **profiles** for Aarav, Rohan and Priya. Tabs in one profile share a session. Multiple private windows commonly share one private session as well. This rental's lender is Priya; Rohan cannot act as lender for it. Priya's admin role also does not permit independent adjudication of her own rental dispute; the existing separation-of-duties rule remains enforced.

The refund UI works in isolated tests. The existing hosted refund remains unsent. The next safe step is to explicitly authorize **one ₹3,400 Razorpay Test refund using this existing clean-return intent**, after reviewing this report. Before any future dispatch, repeat the read-only state/refund-inventory check. If the intent is still unsent and no refund/attempt or dispute appeared, an authorized participant can then use the separate approval and Send control. Retain the ₹500 rental fee and verify the eventual result with gateway GETs and the balanced ledger; do not create another intent or repeat an uncertain POST.

**No new payment, refund, transfer or payout was initiated. No hosted financial or other application records were modified. No hosted migration, commit, push, merge, rebase, reset or deployment was performed. Actual Test refund execution still requires the user's explicit authorization.**
