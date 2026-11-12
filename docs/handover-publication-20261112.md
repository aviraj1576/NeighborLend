# Borrower receipt and publication verification - 12 November 2026

## Scope

The production receipt change is confined to `frontend/src/pages/BorrowRequestDetail.jsx`. Previously the borrower had to select and upload receipt photos before confirming. The existing receipt endpoint already accepts an omitted or empty `photo_urls` list. The UI now sends `photo_urls: []` with the optional condition note, without an upload control or evidence-upload request.

Lender baseline photos remain mandatory. Verified captured payment and both-party confirmation remain mandatory; the rental starts only after lender confirmation. Borrower return photos remain mandatory, followed by lender approval or dispute review. Historical lender, receipt and return evidence remains readable under existing authorization. No backend receipt validation, financial calculation, service boundary, JWT algorithm, AI implementation, trained model or database schema is changed for this receipt adjustment.

The publication also preserves the feature branch's previously approved, uncommitted payment, authentication, teammate-frontend integration, listing-isolation and hosted-initialization guard work. It includes the existing financial and conversation migration artifacts; it does not apply either migration. `.gitattributes` preserves the reviewed conversation SQL's LF checksum on Windows. Private operational reports, credentials, database snapshots and evidence are excluded.

## Final checks

| Verification | Result |
| --- | --- |
| Before-change handover/API baseline | 6 passed; one PostgreSQL case initially skipped before the isolated service was enabled |
| After-change targeted receipt/handover/API contracts | 9 passed, including SQLite and isolated PostgreSQL |
| Complete backend `scripts/verify_payments.py` | 497 passed; zero failed/skipped, isolated SQLite and loopback PostgreSQL |
| Frontend `npm test` | 54 passed |
| Frontend `npm run lint:payments`, `npx eslint src` | Passed |
| Frontend `npm run build` | Vite production build passed |
| New publishable Python files, configured Ruff rules | 25 files passed |
| AI `scripts/verify.py all` with offline hybrid replay | 338 passed; 19 opt-in cases checked separately below |
| Strict AI data-policy cases | 2 passed |
| Genuine native CPU/CUDA cases, isolated fresh processes | 17 passed using existing local cached checkpoints and pinned optional packages |
| AI configured Ruff | Passed |
| Frontend integration Chrome harness | 21 checks passed |
| Listing-conversation Chrome harness | 6 checks passed |
| Payment master / refund / full-App refund-control browser harnesses | 4 / 6 / 12 checks passed |
| Authenticated camera/ladder GET-only API verification | 24 read-only ASGI checks and 8 running-backend GETs passed |

All 357 available AI cases passed across the three runs. The first native attempt omitted the existing optional `kornia` cache from the test process path. Supplying the pinned `.runtime/v3-packages` path resolved the four import failures; all 17 cases then passed without changing AI source, weights or shared packages. The browser harness allows time for cold Vite dependency optimization and retains its assertions and external URL blocks. No real payment or refund dispatch, reconciliation, or provider GET was used for this task.

Backend-wide supplemental Ruff (`E4,E7,E9,F`) is **not clean**: 14 findings (unused imports, ambiguous variable names and legacy import placement) match the committed HEAD diagnostic set exactly. No new finding was introduced. They are recorded as existing lint debt, not silently suppressed or fixed through unrelated refactoring. All configured frontend checks and new-file Python lint pass.

Browser checks use synthetic APIs; the full-App refund harness replays a saved local snapshot with synthetic actions. Desktop/mobile login typography, palette, inputs and navigation match the teammate baseline. Responsive overflow and refund-control hit testing pass at the tested widths. This is targeted visual verification, not an exhaustive screenshot comparison of every page. There is no CSS change for the receipt adjustment.

## Hosted integrity and boundaries

Read-only PostgreSQL checks confirm the recovered listing column, validated foreign key and valid/ready participant-listing unique index. All 11 original conversation IDs, nine listing mappings and two unassigned historical threads are intact. Generic hosted initialization is blocked before DDL; `AUTO_MIGRATE=false` remains in effect. The explicit additive migration helper and isolated local schema workflows remain available.

All 20 non-CAPTCHA application-table fingerprints match the restore-verified recovery snapshot, including accepted offers, requests, bookings, captured payments, immutable journals/ledger, refund intents/attempts, disputes, private evidence and audit history. The short-lived CAPTCHA table differs from that snapshot; no claim of complete 21-table identity is made. Both existing pending refunds (INR 2,000 and INR 200) and their captured-payment links remain unchanged. All 23 live and archived private evidence hashes and the existing restore-verified database backup hash pass.

The task performs no hosted schema/data mutation or Razorpay operation and does not deploy. The updated local backend remains on `AUTO_MIGRATE=false`. A source guard cannot prevent a manually invoked owner SQL session or an old already-loaded process; remote deployment control planes were not independently audited. Live checkout/refund acceptance is deliberately outside this verification.

## Publication contents

The exact reviewed publication paths are listed below. The Git commit is published only to `origin/feature/neighborlend-ai-payment-integration`, without force-push or changing upstream/main. The final operator report records the verified commit SHA after publication. Local recovery archives and private evidence remain outside Git.

- `.env.example`
- `.gitattributes`
- `.gitignore`
- `AGENTS.md`
- `backend/Dockerfile`
- `backend/app/config.py`
- `backend/app/database.py`
- `backend/app/main.py`
- `backend/app/models.py`
- `backend/app/routers/borrow_requests.py`
- `backend/app/routers/chat.py`
- `backend/app/routers/disputes.py`
- `backend/app/routers/payments.py`
- `backend/app/schemas/borrow_request.py`
- `backend/app/schemas/chat.py`
- `backend/app/schemas/payment.py`
- `backend/app/services/auth.py`
- `backend/app/services/conversation_migrations.py`
- `backend/app/services/payment_documents.py`
- `backend/app/services/payment_migrations.py`
- `backend/app/services/payments.py`
- `backend/app/services/rating_eligibility.py`
- `backend/app/services/razorpay_service.py`
- `backend/migrations/payments/003_supabase_financial_guards.sql`
- `backend/scripts/apply_payment_schema.py`
- `backend/scripts/inspect_payment_schema.py`
- `backend/scripts/isolated_payment_postgres.py`
- `backend/scripts/provision_fictional_accounts.py`
- `backend/scripts/run_test_webhook_stack.py`
- `backend/scripts/verify_frontend_integration_browser.py`
- `backend/scripts/verify_jwt_configuration.py`
- `backend/scripts/verify_listing_conversations_browser.py`
- `backend/scripts/verify_master_browser.py`
- `backend/scripts/verify_postgres_master.py`
- `backend/scripts/verify_refund_browser.py`
- `backend/scripts/verify_refund_controls_browser.py`
- `backend/supabase/.gitignore`
- `backend/supabase/migrations/20261112081704_listing_scoped_conversations.sql`
- `backend/tests/conftest.py`
- `backend/tests/test_borrower_receipt.py`
- `backend/tests/test_chat_and_negotiation.py`
- `backend/tests/test_conversation_migrations.py`
- `backend/tests/test_fictional_account_provisioning.py`
- `backend/tests/test_frontend_integration.py`
- `backend/tests/test_jwt_security.py`
- `backend/tests/test_listing_conversations.py`
- `backend/tests/test_payment_finalization.py`
- `backend/tests/test_payment_master.py`
- `backend/tests/test_payment_regressions.py`
- `backend/tests/test_postgres_master.py`
- `backend/tests/test_razorpay_escrow.py`
- `backend/tests/test_refund_workflow_debugging.py`
- `backend/tests/test_schema_initialization_guard.py`
- `backend/tests/test_upstream_api_contracts.py`
- `docs/handover-publication-20261112.md`
- `docs/listing-negotiation-isolation-20261112.md`
- `docs/payment-architecture.md`
- `frontend/eslint.config.js`
- `frontend/index.html`
- `frontend/package.json`
- `frontend/scripts/payment-test-loader.mjs`
- `frontend/src/App.jsx`
- `frontend/src/api/client.js`
- `frontend/src/components/DisputeResolutionModal.jsx`
- `frontend/src/components/EscrowStatusCard.jsx`
- `frontend/src/components/Footer.css`
- `frontend/src/components/Footer.jsx`
- `frontend/src/components/ListingCard.css`
- `frontend/src/components/ListingCard.jsx`
- `frontend/src/components/Navbar.css`
- `frontend/src/components/Navbar.jsx`
- `frontend/src/components/PaymentDocuments.jsx`
- `frontend/src/components/PaymentModal.css`
- `frontend/src/components/PaymentModal.jsx`
- `frontend/src/components/PaymentReviewQueue.jsx`
- `frontend/src/components/RefundPanel.jsx`
- `frontend/src/components/paymentFlow.js`
- `frontend/src/components/payments.test.js`
- `frontend/src/components/ui/Badge.jsx`
- `frontend/src/components/ui/Button.jsx`
- `frontend/src/components/ui/Card.jsx`
- `frontend/src/components/ui/Input.jsx`
- `frontend/src/components/ui/Modal.jsx`
- `frontend/src/context/AuthContext.jsx`
- `frontend/src/context/sessionSync.js`
- `frontend/src/design/global.css`
- `frontend/src/design/skill-kit/backgrounds.css`
- `frontend/src/design/skill-kit/cards.css`
- `frontend/src/design/skill-kit/icon.css`
- `frontend/src/design/skill-kit/layout.css`
- `frontend/src/design/skill-kit/motion.css`
- `frontend/src/design/skill-kit/system.css`
- `frontend/src/design/theme.css`
- `frontend/src/main.jsx`
- `frontend/src/pages/BorrowRequestDetail.css`
- `frontend/src/pages/BorrowRequestDetail.jsx`
- `frontend/src/pages/Browse.css`
- `frontend/src/pages/Browse.jsx`
- `frontend/src/pages/Chat.css`
- `frontend/src/pages/Chat.jsx`
- `frontend/src/pages/CreateBorrowRequest.css`
- `frontend/src/pages/CreateBorrowRequest.jsx`
- `frontend/src/pages/CreateListing.css`
- `frontend/src/pages/CreateListing.jsx`
- `frontend/src/pages/Inbox.css`
- `frontend/src/pages/Inbox.jsx`
- `frontend/src/pages/Landing.css`
- `frontend/src/pages/Landing.jsx`
- `frontend/src/pages/ListingDetail.css`
- `frontend/src/pages/ListingDetail.jsx`
- `frontend/src/pages/Login.css`
- `frontend/src/pages/Login.jsx`
- `frontend/src/pages/MyBorrowRequests.css`
- `frontend/src/pages/MyBorrowRequests.jsx`
- `frontend/src/pages/MyListings.css`
- `frontend/src/pages/MyListings.jsx`
- `frontend/src/pages/Register.css`
- `frontend/src/pages/Register.jsx`
- `frontend/src/pages/VerifyEmail.css`
- `frontend/src/pages/VerifyEmail.jsx`
