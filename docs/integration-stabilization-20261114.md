# NeighborLend integration stabilization — 14 November 2026

Confirmed defects from `backend/.payment-verification/integration-audit-20261114/report.md` are fixed and verified locally. The application is ready for further isolated integration testing with mock payments. This is not hosted-service or real Razorpay sign-off.

No hosted data, migration, secret file, checkpoint, Git history, remote branch, payment-provider implementation, or financial ledger service was changed. Existing unrelated untracked files were preserved. All test servers stopped; the final browser cleanup report contains no process errors.

## Fixes and verification

| Issue | Correction | Evidence |
| --- | --- | --- |
| Missing payment callback; unavailable payment status | Rental page supplies stable `onStatus`/`onBooking` callbacks. Card supports absent optional callbacks, clears parent authority on failed reads, and retains a refresh action even when the first read fails. Controls remain locked until a successful authoritative refresh. | Mounted browser tests cover first-load failure/recovery, checkout capture, later refresh failure/recovery, and zero unhandled exceptions. |
| Independent-admin access | Added protected `/admin/payments` route and navigation. Rental details use the existing authorized private rental API and show authenticated handover/receipt/return evidence to independent admins. Physical participant permissions remain separate. | Browser verifies anonymous redirect, non-admin rejection, admin queue, private evidence, clean refund, dispute decision, and partial refund. Backend tests retain lender/borrower/admin authorization boundaries. |
| Listing chat loses its thread | Listing chat posts both `lender_id` and `listing_id`. Scoped conversations use their returned listing, lock the listing selector, and clear stale chat/draft state on navigation. Legacy general chats retain their existing listing selection. | Real browser reopens an accepted thread with its original offer/history, opens a separate ladder chat, verifies its selected listing, and returns to the original thread. Existing listing/concurrency/backend contract tests pass. |
| Wrong actor sees return upload | Return submission requires matching borrower/rental IDs, captured funding, eligible booking and physical state, and no authorized refund. An admin-authorized disputed return remains available to its borrower. | Component tests cover borrower, lender, outsider, admin, unpaid, missing status, wrong rental, cancellation, refund and completed states. Browser uploads real synthetic PNG evidence through the actual API. |
| Frontend-derived rating eligibility | The page reads `booking.rating_eligible`. The legacy payment-status response now exposes the existing backend eligibility helper too, preserving completed legacy rentals without granting payment authority. | Backend and browser tests reject premature ratings, allow ratings after clean or arbitrated financial settlement, and preserve legacy authorization/funding behavior. |
| Rejected/settled return controls | Lender inspection consults dispute-aware review state and verified booking status. Clean approval/rejection controls disappear after rejection, authorization, approval or settlement. | Component and mounted browser rejection/claim/admin-settlement scenarios pass. |
| Misleading financial labels | Labels distinguish uncaptured, zero-deposit, held, frozen and settled states. Cancellation breakdown uses the backend's processed deposit portion instead of labeling refunded rental fees as refunded deposit. Settled handovers no longer say payment still needs verification. | Component tests and a mounted full pre-receipt cancellation/refund verify ₹900 total refund versus ₹500 deposit refund. |
| YOLO/YOLOE split | `/upload` retains its response contract through a small `ml_service.detect_objects` adapter calling the existing YOLOE classifier. Startup warms that same classifier instead of loading a second YOLO model. The classifier itself, exclusions, confidence setting and checkpoint remain unchanged. | Mock-model tests prove both endpoints return the same classification, honor configured confidence, preserve original class IDs and dumbbell exclusions, and keep uploads working for unavailable/failed/empty inference. |
| Route-inventory parser | Expand JavaScript ternary/receipt variants before stripping URL query parameters. Include payment components and POST helper call sites. No JavaScript evaluation is used. | Parser regressions and all enumerated API route checks pass in the full backend suite. |

## Exact files changed

Application files:

```text
backend/app/main.py
backend/app/routers/payments.py
backend/app/services/ml_service.py
frontend/src/App.jsx
frontend/src/pages/BorrowRequestDetail.jsx
frontend/src/pages/Chat.jsx
frontend/src/pages/ListingDetail.jsx
frontend/src/components/DepositRefundStatus.jsx
frontend/src/components/EscrowStatusCard.jsx
frontend/src/components/HandoverConfirmation.jsx
frontend/src/components/Navbar.jsx
frontend/src/components/PaymentBreakdown.jsx
frontend/src/components/PaymentStatus.jsx
frontend/src/components/ReturnInspection.jsx
frontend/src/components/ReturnSubmission.jsx
frontend/src/components/paymentFlow.js
```

Tests, commands and documentation:

```text
backend/tests/test_frontend_integration.py
backend/tests/test_upstream_api_contracts.py
backend/tests/test_listing_classifier.py                         (new)
backend/scripts/verify_stabilized_integration_browser.py         (new)
frontend/src/components/integration.test.js                     (new)
frontend/package.json
docs/integration-stabilization-20261114.md                       (new)
```

The payment-router addition only exposes the existing legacy rating-eligibility decision. It changes no authorization or accounting rule. Dependencies and the package lock are unchanged; package scripts include the new tests and all affected components in scoped lint.

## Final test results

| Verification | Result |
| --- | --- |
| `npm test` | **74 passed**, zero failed. |
| `npm run lint:payments` | Passed, including changed lifecycle components and new component tests. |
| `npm run build -- --outDir ../backend/.payment-verification/stabilization-20261114/frontend-final-dist` | Passed, 1,684 modules; original `frontend/dist` preserved. |
| Targeted backend classifier/rental/chat/API suites | **80 passed, 5 PostgreSQL cases skipped**. |
| Full backend suite | **505 passed, 23 PostgreSQL-only cases skipped**, zero failed. |
| Scoped Ruff: classifier adapter, new classifier tests, API inventory, browser regression script | Passed. |
| `verify_stabilized_integration_browser.py` final run | **13 scenarios passed**, zero unhandled browser exceptions; clean process shutdown. Real React and local FastAPI, generated SQLite, mock payments, actual private evidence uploads. |
| `git diff --check` | Passed. |

The first browser attempt had an incorrect test expectation that accepted offers permit new offers; the test now checks the existing accepted history and a new listing's selection separately. The second attempt passed all twelve then-current scenarios but timed out during Chrome cleanup. Cleanup was corrected and the final thirteen-scenario run exited successfully. No application behavior was loosened to accommodate those harness failures.

Backend execution used the installed Anaconda Python 3.11, `PYTHONPATH=.test-tools;.`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, no `PAYMENT_TEST_POSTGRES_URL`, generated SQLite fixtures, and forbidden real provider transport. Artifact folders are new and isolated under `backend/.payment-verification/stabilization-20261114/`.

Key evidence:

```text
backend/.payment-verification/stabilization-20261114/backend.xml
backend/.payment-verification/stabilization-20261114/targeted.xml
backend/.payment-verification/stabilization-20261114/browser-final/results.json
backend/.payment-verification/stabilization-20261114/browser-final/cleanup.json
backend/.payment-verification/stabilization-20261114/browser-final/independent-admin-review.png
backend/.payment-verification/stabilization-20261114/frontend-final-dist/
```

Checkpoint SHA-256 before/after: `043baf1fb0a45a923a3deee709295fa62782e6d4d5473547d5a7a6a686ce8eca`. Financial services, provider adapters, schema models, migrations, JWT settings and database configuration have no diff.

## Remaining integration risks

- Real Razorpay Test checkout, gateway refunds/webhook delivery, hosted Supabase schema/storage, SMTP and Google OAuth were not contacted. Their configuration requirements from the audit remain. No claim is made about their current availability.
- Native checkpoint inference/accuracy was not exercised; model integration was tested with synthetic models and failure injection. No model training, download or checkpoint change was performed.
- The 23 PostgreSQL cases were intentionally skipped under this task's SQLite-only testing constraint. No new schema/migration is required for these fixes.
- No frontend type-check command is configured. Public deployment still requires a configured HTTPS `VITE_API_BASE_URL` ending in `/api`; the local Vite build is not a deployment readiness check.

## Safe local start (PowerShell, two terminals)

The existing audit launcher creates a new isolated SQLite demo, generates a private process-only JWT, clears external gateway/storage/mail credentials in Python, seeds local accounts, and starts the real FastAPI application with mock payments. It leaves `backend/.env` and existing application data unchanged. Optional model preload is skipped.

```powershell
Set-Location D:\neighborlend_project\NeighborLend\backend
& 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe' -B .payment-verification/integration-audit-20261114/start_local_demo.py
```

Enter a new private 12–72-byte demo password when prompted. Then:

```powershell
Set-Location D:\neighborlend_project\NeighborLend\frontend
$env:VITE_API_BASE_URL = '/api'
$env:BACKEND_PROXY_TARGET = 'http://127.0.0.1:8000'
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open `http://127.0.0.1:5173`. Sign in as `demo_borrower`, `demo_lender` or `demo_admin` using the privately entered password. Administrator review is at `/admin/payments`. Local registration email/Google OAuth are not configured by the isolated launcher; the seeded accounts avoid calling those services.

To rerun mounted browser verification from `backend/`:

```powershell
& 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe' -B scripts/verify_stabilized_integration_browser.py
```

This creates a new verification folder automatically and stops its loopback servers. It does not depend on the interactive demo or use its credentials/data.
