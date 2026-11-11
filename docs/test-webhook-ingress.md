# Razorpay Test webhook ingress

Current completion: [final release audit, 11 November 2026](payment-final-release-audit-20261111.md). All three payments and both A/B refunds are verified through official Test GETs. Correlated processed webhook receipts exist, but independent Dashboard delivery provenance remains **NOT VERIFIED**. The preparation and delivery observations below are historical; do not repeat checkout, refunds or synthetic deliveries against the preserved database.

The subsequent [sandbox-only hardening report](sandbox-only-payments.md) documents startup/dispatch guards, explicit frontend sandbox confirmation, minimized new webhook receipts, and preservation checks. Its verification does not complete the prepared checkout or initiate refunds.

The full API keeps `DEPLOYMENT_EXPOSURE=local`. Its transport guard still rejects public hosts and forwarded requests. A separate reverse proxy accepts only an exact `POST /api/payments/webhook`; every other path/method, including docs, health, auth, uploads, order creation and admin routes, returns 404.

The proxy checks the existing test-only provider configuration, raw-body HMAC, unique signature/event headers, a 128,000-byte limit and a body deadline before forwarding to the fixed loopback URL `http://127.0.0.1:8001/api/payments/webhook`. It strips inbound authorization, cookies and forwarding headers and never follows redirects or uses environment proxies. The application verifies the same original bytes again and retains durable receipts, duplicate detection, payload-conflict rejection and authoritative financial reconciliation.

## Environment loading

`Settings` loads absolute paths in this order: project-root `.env`, then `backend/.env`. Process variables override both files. The backend file is not copied into the frontend. Vite continues reading only the shared root and only exposes `VITE_` variables; never put private keys, webhook secrets or JWT secrets in `VITE_` variables. Validation errors hide input values. Tests explicitly shadow real Razorpay fields with empty process values before loading application modules.

No existing credential values are changed. The existing backend process must be restarted to use source/config changes; the verification stack starts independent fresh processes and leaves the existing process and data untouched.

## Start the isolated local stack

From `D:\neighborlend_project\NeighborLend\backend`:

```powershell
& 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe' -B scripts/run_test_webhook_stack.py
```

This starts a private API on **127.0.0.1:8001** and the webhook proxy on **127.0.0.1:8010**. It explicitly creates a new isolated SQLite database under `backend/.payment-verification/webhook-ingress-20261110-01/`. It never migrates, opens or resets the existing application database, starts a tunnel, loads AI models, or performs a payment/refund. Stop the foreground controller with Ctrl+C to stop its children. Runtime process IDs and isolated DB location are in `stack-state.json`; do not launch a second stack while these ports are occupied.

Run local verification:

```powershell
& 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe' -B scripts/verify_test_webhook_ingress.py
```

The verifier signs an informational synthetic `refund.created` with the configured secret, sends it through both processes, checks duplicate/tamper/conflict/body-limit handling, verifies denied routes and confirms no user/financial state changes. It prints no credentials or signatures. Local success proves the verifier, proxy and backend agree on the secret; it cannot prove the independently configured Razorpay Dashboard secret matches.

## Restart Cloudflare only when ready

Keep the stack running, then run:

```powershell
cloudflared tunnel --url http://127.0.0.1:8010
```

Use the new HTTPS origin printed by Cloudflare plus **`/api/payments/webhook`** in the existing **Test Mode** Dashboard webhook. The old Quick Tunnel URL is not assumed active. Do not point Cloudflare at ports 8000 or 8001. Keep the existing webhook secret and API keys; only update the URL when necessary. No external diagnostic service is needed.

Once the new tunnel is running, verify its origin (without the webhook path):

```powershell
& 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe' -B scripts/verify_test_webhook_ingress.py --base-url https://YOUR-NEW-HOST.trycloudflare.com --allow-public-test
```

This remains an isolated synthetic webhook test, not a checkout or refund. A Dashboard-originated Test webhook or redelivery is still needed to independently establish that the Dashboard uses the same secret. No secret should be pasted into chat, screenshots, CLI arguments or frontend configuration.

## Selected events

| Event | Handling |
| --- | --- |
| `payment.authorized` | Fetch authoritative payment/order state; never unlock custody based on an authorization payload alone. |
| `payment.captured` | Reconcile verified captured payment and apply idempotent ledger rules. |
| `payment.failed` | Reconcile authoritative state; late failures cannot downgrade capture. |
| `order.paid` | Fetch order payments and require exactly one captured payment before reconciliation. |
| `refund.created` | Authenticate, validate refund identifier, durably record and acknowledge as informational; no refund state or ledger mutation. |
| `refund.processed` | Require a known authorized refund intent and fetch authoritative refund state before settlement. |
| `refund.failed` | Reconcile authoritative refund failure; never create an unauthorized refund or silently retry it. |

`refund.created` and successful processing are distinct events in [Razorpay's refund webhook documentation](https://razorpay.com/docs/webhooks/refunds/). Creation alone does not authorize a refund or establish financial completion. Unknown orders/refund intents remain rejected/pending reconciliation rather than creating local financial authority.

## Readiness boundary

Local ingress security can be verified with the tunnel stopped. Public synthetic delivery through the new tunnel has now passed; independent Dashboard-side secret consistency and Razorpay-originated delivery remain unverified. End-to-end test checkout and refund execution have not been performed by this setup. The isolated database is a webhook fixture, not a copy of existing users or bookings. A future checkout must use authenticated test users and agreed test bookings in that same isolated API; its local frontend proxy would target port 8001. Do not combine port-8000 orders with port-8001 webhook storage.

## Verification on 10 November 2026

- **PASS:** 119 payment/provider, ingress, authorization, refund-state and CAPTCHA regressions. These use isolated databases and synthetic provider transport; refund/capture simulations do not call Razorpay.
- **PASS:** Actual local TCP delivery through proxy 8010 to API 8001 with the unchanged configured webhook secret. Signed informational delivery returns 200; duplicates return 200; tampering/invalid signatures return 400; signed identifier/body conflicts return 409; oversized bodies return 413.
- **PASS:** Other ingress routes return 404; spoofed public/forwarded requests to the private API return 403. No user/booking/payment/refund/journal row counts change during the informational webhook test. Durable webhook receipt matches the exact signed bytes.
- **PASS:** All seven selected event handlers are exercised, including authoritative `order.paid`, `refund.processed` and `refund.failed` reconciliation, and informational `refund.created` deduplication. A terminal refund callback cannot send a second refund POST.
- **PASS:** New-file Ruff lint/format checks and syntax/static checks on modified backend modules. Credential files remain unchanged; no frontend secret variables were found.
- **Earlier local evaluation:** Public delivery was deferred while the user intentionally kept the tunnel stopped. The public verification below supersedes that connectivity limitation. No tunnel was started by the agent.

Reproduce the regression suite from `backend/` with `PYTHONPATH=.test-tools;.` and `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`:

```powershell
python -B -m pytest tests/test_webhook_ingress.py tests/test_payment_providers.py tests/test_razorpay_escrow.py tests/test_payment_regressions.py tests/test_payment_v3_hardening.py tests/test_auth_captcha.py -q
```

XML and local TCP observations are retained under `backend/.payment-verification/webhook-ingress-20261110-01/`. An initial targeted run had six temporary-directory setup errors; after creating the missing output parent, all 36 targeted checks passed, followed by the final 119-test regression run. No application/test behavior was weakened to clear a failure.

## Public verification on 10 November 2026

The user restarted Cloudflare and updated the Test Mode webhook to `https://missouri-evidence-patches-fiscal.trycloudflare.com/api/payments/webhook`. Executed from `backend/`:

```powershell
& 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe' -B scripts/verify_test_webhook_ingress.py --base-url https://missouri-evidence-patches-fiscal.trycloudflare.com --allow-public-test
```

- **PASS: Public reachability and signed synthetic processing.** All 21 existing verifier checks passed. A signed informational `refund.created` was durably acknowledged with 200; its repeat returned duplicate 200. Invalid/missing signatures and tampered bytes returned 400; signed payload/event-ID conflict returned 409; an oversized body returned 413.
- **PASS: Proxy isolation.** Existing negative GET probes passed. Nine additional public probes covering POST order creation, login, admin/settlement routes, GET/OPTIONS webhook, trailing slash, encoded path and query-based forwarding all returned 404. The private API continues rejecting spoofed public/forwarded requests with 403.
- **PASS: Data and credential preservation.** All isolated user, booking, payment, refund-intent and journal counts remained zero. Only synthetic webhook receipts were added. Existing user storage was not accessed, credential-file hashes were unchanged, and no checkout, capture or refund occurred.
- **NOT VERIFIED: Actual Razorpay-originated delivery and Dashboard-secret matching.** The isolated database contains three processed `refund.created` receipts, all identified as this verifier's synthetic events. Available server logs contain no delivery evidence. No connected Dashboard session or exported Razorpay delivery record is available. These synthetic tests prove secret agreement across the verifier/proxy/backend only; they do not independently establish the Dashboard secret or actual Razorpay-originated delivery.

Remaining blocker: a genuine Dashboard Test delivery/redelivery and its delivery record must be observed before claiming Razorpay-originated verification. Do not change or display the webhook secret. Checkout/capture/refund execution remains deferred.

Evidence is retained in `backend/.payment-verification/webhook-ingress-20261110-01/public-verification.json` and `public-delivery-audit.json`. No application source changes, Git commits, branches or pushes were made during this public verification.

## Prepared manual Test checkout on 10 November 2026

One authorized **INR 1.00 / 100 paise** order is ready in the same isolated database. Its order ID is `order_TyYcyFgRliMilB`; booking ID is `a9274a7e-2bce-421d-8f43-f62d4c34b769`. The rental fee is INR 1.00 and the security deposit is zero. The provider reports `created`, amount paid zero, and no payment attempts at preparation time. No payment has been completed by the verification scripts.

The isolated database had no users or listings. Two non-admin, verified fixture accounts and one test listing were added there; existing application user storage was not opened. Both accounts authenticated through the real login API. The borrower submitted the offer, the lender accepted it through the application, and only the authenticated borrower could create the order. Anonymous and lender order creation were rejected. Repeating borrower order creation returned the same provider order, and an authenticated provider GET confirmed its amount, currency, receipt and booking association.

A separate React development server is running on **127.0.0.1:5175**, using process-only `VITE_API_BASE_URL=/api` and `BACKEND_PROXY_TARGET=http://127.0.0.1:8001`. The existing API, proxy and tunnel were preserved. Authenticated requests through this frontend resolve to the prepared isolated booking; private credential files are denied by Vite. No backend secrets are supplied to the frontend. The generated account-password file is ignored by Git, outside the frontend, and restricted to the current Windows account.

Manual steps:

1. Open `backend/.payment-verification/webhook-ingress-20261110-01/checkout-accounts.json` locally. Use only the `borrower` username and password; do not share that file or paste its contents into chat.
2. Visit <http://127.0.0.1:5175/login> and sign in normally with that account.
3. Open <http://127.0.0.1:5175/borrow-requests/bb32b569-39e1-4127-928f-5860920ae060>.
4. Confirm **TEST MODE**, rental INR 1.00, deposit INR 0.00, total INR 1.00. Select **Pay test rental + deposit**.
5. In Razorpay Test Checkout, select **Netbanking**, choose any available listed bank, then select **Success** on the mock bank page. This is the flow documented in [Razorpay's official Test Integration instructions](https://razorpay.com/docs/payments/payment-gateway/web-integration/standard/integration-steps/#2-test-integration). Complete only this test payment. Leave cancellation, handover, refund and deduction controls untouched.
6. Keep the API, proxy, tunnel and browser page running. Report that the test payment is complete so the genuine event receipts and funding ledger can be inspected. If payment remains authorized rather than captured, do not trigger a separate capture or refund; report that status for review.

Preparation verification: **PASS** for normal borrower/lender authentication, lender agreement, 100-paise Test order, order idempotency, frontend-to-isolated-API association, private-file denial, 25 frontend tests and the Vite production build. All 21 public webhook ingress checks were rerun successfully, including invalid signatures and duplicate detection, without changing the current isolated user/financial state. Credential files remain unchanged. The read-only baseline contains two fixture users, one booking, one order transaction, zero funding journals, zero refund intents and no correlated payment-capture/order-paid webhook receipts.

**Pending manual payment:** genuine `payment.captured` / `order.paid` delivery, provider-confirmed capture, funded booking, one balanced funding journal, and any actual provider redelivery evidence. Synthetic webhook tests do not establish Dashboard-secret matching. No Dashboard delivery record is available yet. No checkout completion, capture API call, refund, deduction, AI integration, commit or push was performed during preparation.

After the manual payment, the following audit reads only this isolated database and performs provider GET requests; it never signs events, reconciles application state, captures or refunds:

```powershell
# From backend/
& 'D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe' -B .payment-verification/webhook-ingress-20261110-01/verify_checkout_result.py
```

Preparation state, UI checks and the pending result are retained as `checkout-state.json`, `checkout-ui-verification.json` and `checkout-result.json` in the same ignored artifact directory. The React process ID is in `checkout-ui-state.json`. The existing 8001/8010 controller remains unchanged. The booking starts on 11 November; if testing is postponed, its dates and payment eligibility must be reviewed before reuse.
