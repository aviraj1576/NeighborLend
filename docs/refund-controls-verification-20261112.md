# Refund controls, footer overlap, and administrator policy — 12 November 2026

## Confirmed causes

The original blocked Send button was a layout/hit-testing failure, not a missing approval flag or an API rejection. A full Chrome render of the actual `App` used authenticated, read-only backend responses for rental `0d2d9947-bc15-43cb-87e5-ca7c4b3042c4`.

At 1440 × 900, the shared design kit fixed the rental page at 1800px while its card needed approximately 2251px. The footer began roughly 571px before the card ended. Its stylesheet existed but was not imported. The full-width `.footer-logo` consequently overlapped the approved Send button.

The approval checkbox had `disabled=false` and received real mouse input. Selecting it enabled Send (`disabled=false`, `pointer-events:auto`), but `document.elementFromPoint()` at Send's center returned `DIV.footer-logo`. Coordinate-based Chrome input reached that footer element in both capture and bubble phases. The React refund handler did not receive the click. There was no modal or fixed/absolute overlay at the control; the two positioned `.wrap` elements had `z-index:1`, and the later footer content painted over the overflowing rental content.

The previous refund policy separately allowed participants to operate refunds. That behavior has been changed at the user's explicit request: only administrators can dispatch, retry, or invoke refund reconciliation. Participants retain status visibility and their existing physical-return responsibilities.

## Financial findings and later manual dispatch

Read-only Supabase and Razorpay checks initially showed:

| Item | Result |
| --- | --- |
| Authenticated operator | `priya_sharma`, database-derived administrator, neither participant |
| Borrower / lender | `aarav_mehta` / `rohan_kapoor` |
| Capture / rental fee / deposit | ₹2,500 / ₹500 / ₹2,000 |
| Physical return | Confirmed, four return photographs |
| Refund | Authorized by lender, `created`, zero attempts, no gateway refund |
| Financial journal | Balanced, no deduction |

The user subsequently clicked the now-accessible controls during this work. A fresh read-only investigation of the reported screenshot found **one ₹2,000 Razorpay refund in `pending` status**, matching the saved intent and payment. Four application attempts refer to the existing refund; the gateway inventory contains one refund, not four. Razorpay's payment object reports ₹2,000 in `amount_refunded`, but the refund object itself remains `pending`. That aggregate field is not treated as proof of completed settlement. The application correctly retains ₹2,000 of pending liability and records no completed deposit refund.

The repeated historical `refund_requested` entries included status checks. Future checks now use `refund_status_check_requested`; existing hosted audit history was not rewritten. A pending refund is already submitted and must not be recreated.

The final deeper inspection found **five** application checks sharing **one** provider refund ID. The gateway still reported `pending`, `speed_requested=normal`, `speed_processed=normal`, no error code, and no acquirer/bank reference. No matching refund-webhook receipt exists in the application database. Only the API listener on port 8000 was active locally; the webhook ingress on 8010 was not running. The API launcher has reload enabled. Lack of webhook delivery affects automatic final-status updates but cannot explain away a refund that the gateway itself still reports as pending. No public tunnel or webhook configuration was created because all work was restricted to local changes.

Razorpay documents that accepted refunds can remain pending and that final status must be confirmed through the refund API/webhook: [Refund FAQs](https://razorpay.com/docs/payments/refunds/faqs/). Test Mode does not move real money: [Razorpay Test Mode explanation](https://razorpay.com/blog/instant-payment-gateway-activation-india/). No application change can safely turn a genuinely gateway-pending refund into a completed one.

## Exact changes

| Files | Changes |
| --- | --- |
| `frontend/src/pages/BorrowRequestDetail.css` | Scoped content-driven height for the rental page and its wrapper. Preserve the existing minimum screen count, padding, card widths, colors, and typography. |
| `frontend/src/components/Footer.jsx` | Import the existing `Footer.css` so the intended footer design is actually applied. |
| `frontend/src/components/Footer.css` | Let the footer and wrapper grow with their content while retaining the minimum screen height and existing responsive grid. No z-index or pointer-events workaround. |
| `frontend/src/components/paymentFlow.js` | Refund-operation permissions require `user.is_admin === true`. |
| `frontend/src/components/RefundPanel.jsx` | Independent admin guard even if a stale caller passes `allowed=true`. Participants see status without operation controls. Explain accepted-but-pending gateway refunds, prevent implying completion, and display the saved provider refund reference. |
| `backend/app/routers/payments.py` | Execute/reconcile routes depend on `require_admin`. The compatibility `refund-deposit` endpoint can authorize an eligible lender-confirmed return but no longer dispatches or reconciles. |
| `backend/app/routers/borrow_requests.py` | Remove automatic mock refund execution after lender return confirmation. Return confirmation creates authorization; an admin must execute settlement separately. |
| `backend/app/services/payments.py` | Verify the dispatch operator's actual database admin role, including direct service calls and retries. Guard mock reconciliation before mutation. Label GET-only checks separately from new dispatch requests. Preserve allocation checks, idempotency, posting invariants, and verified webhook reconciliation of existing gateway outcomes. |
| `backend/scripts/verify_refund_controls_browser.py` | New full-App Chrome regression using actual styles, native coordinate clicks, Space/Tab/Enter, hit-testing, computed stacking/overlay inspection, and screenshots. Live bridge forwards GETs only and refuses mutations. Financial interactions run in isolated memory fixtures. Uses a separate Vite optimizer cache and cleans up owned process trees. |
| `backend/scripts/inspect_refund.py` | Add GET-only diagnostics for processing speed, provider errors, bank-reference availability, unique attempt refund IDs, and received refund-webhook metadata. |
| `backend/scripts/verify_refund_browser.py` | Admin dispatch fixtures and participant-denial expectations reflect the new policy. |
| `frontend/src/components/payments.test.js` | Add admin-only/stale-permission checks and pending-refund/reference presentation checks. |
| `backend/tests/test_refund_workflow_debugging.py` | Add participant/outsider operation denial, forged admin-flag denial, legacy-path safety, GET-only pending reconciliation, single-dispatch checks, and confirmation-gated posting checks. |
| `backend/tests/test_razorpay_escrow.py` | Positive refund-operation helper defaults to admin; denial tests specify actors explicitly. Clean-return test now proves lender confirmation leaves funds pending until admin execution. |
| `backend/tests/test_payment_master.py`, `test_payment_regressions.py`, `test_payment_finalization.py`, `test_postgres_master.py` | Existing direct refund-service/concurrency fixtures use the authorized admin operator. Financial assertions remain intact. |

## Intentional disabled states

| State | Administrator | Borrower/lender without admin privileges |
| --- | --- | --- |
| Authorized, not dispatched | Checkbox available; Send disabled until explicit approval; reconcile disabled because there is no submitted refund | Status and amounts only |
| Operation busy | Controls disabled during the operation | Status only |
| Gateway pending | Reconcile available; another Send is not offered | Pending status and saved reference |
| Confirmed failed refund | New admin consent required for the controlled retry path | Status only |
| Processed | Completed status; no operation buttons | Completed status |

Verified gateway webhooks may still confirm an already submitted refund. They cannot use the reconciliation path to create a new Razorpay refund. This preserves asynchronous payment correctness while keeping human refund operations admin-only.

## Verification

- Final full backend suite: **437 tests passed**, including the dedicated local PostgreSQL ledger/concurrency cases; no skipped tests.
- Frontend: **54 tests passed**; payment/Footer ESLint and production build passed.
- New full-App browser suite: **12 checks passed**, covering admin native Send/reconcile, borrower/lender status-only access, 1440/1280/1024/768/390px widths, expanded financial history, no footer overlap, no horizontal overflow, and keyboard access.
- Existing integration browser suite: **20 checks passed**.
- Updated refund browser suite: **6 checks passed**, including admin consent, lost-response recovery without resend, retry consent, and outsider denial.
- Ruff on changed payment routes/service and new regression tooling passed.

Initial failures were the reproduced footer hit target, the reproduced old participant refund policy, and browser-driver timing/keypress issues corrected in the regression tool. The application uses native keyboard behavior; no keyboard interception was added to payment components.

Local evidence is under `backend/.payment-verification/refund-controls-20261112/`: `before.json`, `before.png`, `after.json`, `after.png`, and read-only refund snapshots. The initial snapshot predates the user's manual dispatch. The later `pending-review/` snapshot records that user-triggered state separately. No claim is made that user activity left hosted history unchanged across those two stages.

## Manual follow-up

Restart the local FastAPI process if it does not reload changed source, then refresh the frontend. Admins can operate refunds; borrowers and lenders can view status. For the already submitted ₹2,000 refund, use its saved reference in the Razorpay **Test Mode** Dashboard. Once the gateway confirms processing, use admin reconciliation or the verified webhook to reflect completion. Do not create another intent or resend a pending refund. Native model services and external AI availability were not retested because this change does not touch them.

All agent financial checks were read-only; financial browser/backend tests used isolated fixtures. No hosted financial records, migrations, gateway payments/refunds/transfers, Git history, or deployment were changed by the agent. The unresolved external condition is the gateway's actual `pending` refund status.
