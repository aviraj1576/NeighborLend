# Integration bug fixes — 12 November 2026

The security-deposit refund approval flow is accessible through the administrator review queue and was exercised from the queue link through approval, synthetic dispatch, and status refresh. The existing camera refund was inspected only; it was never dispatched.

## Read-only financial findings

Rental: `38af43ff-454f-4413-beda-6f84c9a4034f`.

| Check | Verified result |
| --- | --- |
| Borrower / actual lender | `aarav_mehta` / `priya_sharma` |
| Gateway payment | ₹3,900 captured, INR |
| Rental fee / deposit | ₹500 / ₹3,400 |
| Physical return | Lender confirmed; four return photographs recorded |
| Refund authorization | `clean_return`, `created`, ₹3,400; authorized by the actual lender |
| Dispatch attempts / gateway refund identifier | Zero / absent |
| Gateway refund inventory / refunded amount | Empty / ₹0 |
| Deposit liability / reserved refund | ₹3,400 / ₹3,400 |
| Deductions | ₹0 |
| Posted journal | Balanced |

The refund is authorized and awaiting a separate dispatch approval. It is not a completed gateway refund. No evidence of a failed refund dispatch exists for this rental.

`inspect_refund.py` enforced `BEGIN READ ONLY`, transaction rollback, and GET-only Razorpay requests. A fresh task-specific table fingerprint was saved before implementation; the final fingerprint matched. Local diagnostic artifacts are under `backend/.payment-verification/integration-fixes-20261112/`. The script's older historical baseline was not used as this task's before/after baseline.

## Root causes and exact changes

| Files | Change and reason |
| --- | --- |
| `backend/app/routers/disputes.py` | The admin queue previously selected only failed/unknown refunds. It now includes `created`, `dispatching`, and `pending` intents and exposes refund metadata and actual participant IDs. It remains admin-only and performs no dispatch. |
| `frontend/src/components/PaymentReviewQueue.jsx`, `paymentFlow.js` | Label authorization, dispatch, uncertainty, and provider confirmation separately. Add loading/error handling; failed reads no longer say there are no unresolved cases. Ignore superseded queue responses. |
| `frontend/src/components/EscrowStatusCard.jsx` | Guard financial actions against duplicate clicks and invalidate outstanding status reads when the component is cleaned up. Preserve the existing separate execute/reconcile endpoints and refresh after either mutation outcome. |
| `frontend/src/components/RefundPanel.jsx` | Disable approval changes while an action is busy. Retain explicit amount-specific consent before Send and fresh administrator consent for retrying a confirmed failed refund. |
| `frontend/src/api/client.js`, `context/sessionSync.js` | Associate responses with the session that sent the request. A previous session's 401 cannot erase a newer token; successful old responses cannot restore private data. Current-session expiry broadcasts an in-tab identity invalidation. |
| `frontend/src/context/AuthContext.jsx` | Clear displayed identity on invalidation, fence superseded sign-in/bootstrap responses, preserve the token on transient bootstrap failures, and discard account-specific component state when identity changes. Login, verification, and Google sign-in retain the backend's token/user response contract. |
| `frontend/src/pages/BorrowRequestDetail.jsx` | Reset state when rental/account changes, invalidate old reads, and require borrower receipt photographs before enabling confirmation. Existing lender identity and both-party handover remain authoritative. |
| `frontend/eslint.config.js` | Include changed authentication and API files in ESLint coverage. |
| `backend/tests/test_refund_workflow_debugging.py` | Reproduce the missing queue entry, verify non-admin denial and read-only queue behavior, exercise explicit admin approval through synthetic transport, and prove repeated execution makes one synthetic refund with balanced accounting. |
| `backend/scripts/verify_frontend_integration_browser.py` | Add admin queue-to-approval/dispatch and authentication-race browser checks. Align the harness router with the application, enforce required receipt evidence, reject failed test-server startup, and scope timeout cleanup to test-owned processes. |
| `backend/scripts/verify_refund_browser.py`, `frontend/src/components/payments.test.js` | Add initial admin dispatch coverage, session invalidation regression tests, and distinct refund-state labels. |

JWT signing, database-derived admin authorization, ownership checks, independent administrator deduction review, immutable allocation rules, provider idempotency, and AI advisory boundaries were retained. No financial service or schema change was needed. No CSS, typography, navigation, or layout was edited in this task. The Vite CSS output remained `index-Dmtm_TKU.css`, matching the pre-change build. YOLOE identification and damage-inspection implementations were unchanged.

## Verification

| Verification | Final result |
| --- | --- |
| Full backend suite, `scripts/verify_payments.py` | **435 passed**, using generated SQLite databases and the dedicated loopback PostgreSQL test database |
| Frontend, `npm test` | **52 passed**, zero skipped |
| Integrated headless-browser checks | **20 passed**; includes admin queue → consent → synthetic Send → pending status, identity races, both-party handover, private photos, return, rating gates, and design comparison |
| Refund headless-browser checks | **8 passed**; borrower/lender/admin approval, exact payload, pending/reconcile, receipts, lost responses, failed retry consent, outsider denial |
| AI evidence boundary/API/security regressions | **31 passed**, synthetic inputs and mock model/provider adapters |
| Vite production build | Passed |
| Payment ESLint and explicit auth/API ESLint | Passed, zero warnings |
| Changed frontend formatting checks | Passed |
| Ruff on changed backend route/test/browser scripts | Passed |
| Scoped `git diff --check` | Passed |
| Final hosted/gateway read-only inspection | Financial state unchanged; task-specific table fingerprints matched |

The new queue regression failed before the fix because the authorized rental was absent. During verification, the browser harness also exposed its router-placement assumption and a browser-shutdown timeout; both were corrected and the final run exited successfully with freshly started test servers. No final regression failures remain.

The backend runtime used was `D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe`; the shell's default Python is not usable for this backend. PostgreSQL tests used only `127.0.0.1:57927/neighborlend_test_regressions`, never the hosted application URL. Gateway credentials were cleared by backend test setup, transport was synthetic, and browser tests blocked hosted API/provider URLs.

AI coverage: `tests/unit/test_boundary.py`, `tests/unit/test_contracts.py`, `tests/security/test_access.py`, `tests/security/test_cv_output_validation.py`, `tests/integration/test_cv_boundary_advisory.py`, `tests/integration/test_api.py`, and `tests/regression/test_phase3_safeguards.py` under `ep/`. Native model inference and external AI-provider availability were not revalidated.

## Manual retest — left to the user

1. Restart the local FastAPI process so it loads the route changes, refresh the frontend, and sign in again. Use separate browser profiles for simultaneous borrower, lender, and admin testing; tabs in one profile intentionally share the session.
2. Create a fresh rental agreement. Confirm handover stays locked before capture, then perform the Razorpay Test payment manually. Upload lender handover photos, upload borrower receipt photos and confirm receipt, then have the actual lender confirm activation.
3. Upload borrower return photographs. Have the lender confirm the clean return. Confirm the refund is authorized, with the correct deposit amount, and is not labelled completed.
4. As admin, open `/payment-review`, follow **Refund authorized — awaiting dispatch approval**, select the amount-specific approval checkbox, and use **Send approved Test refund** only when deliberately conducting your manual test. The Send button must be disabled before approval. A pending gateway result must remain pending; use reconciliation to check its outcome. The refund acknowledgment appears only after confirmed processing. The ₹500 rental fee remains separate; lender allocation sends no transfer.
5. In a separate fresh rental, reject the return condition, submit a lender claim with evidence, and respond as borrower. Verify neither participant can approve a deduction. An independent admin must enter a reason and a bounded deduction, including zero when rejecting the claim; AI evidence remains advisory.
6. For the existing camera rental, use the saved ₹3,400 intent if you later choose to test its dispatch. Do not recreate the intent or record authorization as a completed refund. After an uncertain response, inspect/reconcile status before another deliberate action.

No application blocker remains in the isolated checks. Actual gateway execution and the fresh manual end-to-end test remain intentionally unperformed. No hosted records, Supabase schema, gateway financial operations, Git history, or deployment were changed.
