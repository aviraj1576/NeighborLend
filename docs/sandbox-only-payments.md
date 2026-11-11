# Sandbox-only payment enforcement

Current completion and release limits: [final release audit](payment-final-release-audit-20261111.md) and [implemented architecture](payment-architecture.md). A/B refunds are processed. The historical database lacks payment migration triggers and the active local signing key fails public-deployment strength policy; the passing application guards below must not be read as a production-readiness claim.

Current lifecycle implementation, independent reviewer rules, explicit refund approval, prepared ₹2,500 scenarios and final verification results are in [payment lifecycle finalization](payment-lifecycle-finalization.md). Historical verification evidence below is retained. Return confirmation no longer dispatches Razorpay refunds; the explicit approved execution action is required.

NeighborLend supports only `disabled`, explicitly enabled local `mock`, and `razorpay_test`. There is no live provider implementation or switch that enables live payments. This is an application boundary, not a claim of absolute security against a compromised runtime, replaced frontend, or payment provider.

## Enforced invariants

- Provider selection is a strict literal and is revalidated at runtime. An absent provider defaults to `disabled`, which cannot dispatch payments. Unknown, blank and ambiguous provider selections fail configuration validation.
- Any nonempty API Key ID must match `rzp_test_[A-Za-z0-9]+`, including when payments are disabled. Partial or blank credential sets fail closed. A complete Test credential set may remain parked under `disabled` without granting dispatch authority.
- `mock` requires explicit demo mode, direct loopback deployment and no Razorpay credentials. `razorpay_test` requires the complete Test configuration and rejects simultaneous demo mode. The deprecated `MOCK_PAYMENTS` flag grants no authority.
- The cached Razorpay adapter revalidates its source configuration, selected mode, key prefix and cached credential consistency before each network dispatch and checkout/webhook HMAC operation. Live-key injection or configuration changes stop operations before transport.
- Gateway HTTPS dispatch uses a fixed official `api.razorpay.com/v1/` origin, verified HTTPS, no environment proxy and no redirects. An operation allowlist permits order creation, authorized Test refunds and required reconciliation GETs. Capture, payouts, marketplace transfers, account management and settlement endpoints are denied. Explicit live-mode provider responses are rejected.
- Only the authenticated borrower can create or verify an order or request payment reconciliation. Order creation uses an accepted, authorized booking and server-calculated financial snapshots. Client-supplied amounts, currency, provider, keys and sandbox flags are rejected as extra fields.
- Before dispatch, booking amounts must be actual Python integers: duration 1–3650 days, positive daily rate, nonnegative deposit, rental fee equal to daily rate times duration, total equal to fee plus deposit, total positive and at most 1,000,000,000 paise, and currency exactly INR. Stored order snapshots must still match the booking.
- Booking and checkout responses derive `sandbox_only` from validated backend provider state. React requires literal `sandbox_only: true` and `test_mode: true`, matching booking/order identifiers, a Test key and valid integer-paise INR amounts before loading Razorpay Checkout. Financial dispatch permissions also require the backend's operations-enabled flag.
- React displays **RAZORPAY TEST MODE — NO REAL MONEY**. Concurrent checkout calls share a single in-flight operation and dialog. Backend durable order intents and journal references remain idempotent.
- Razorpay's official hosted checkout remains responsible for simulated banking/card input. The payment flow forwards only booking ID, order ID, payment ID and signature from its callback. It does not implement banking-password, card, payment-OTP or UPI-PIN forms or persistence.
- New webhook receipts retain only allowlisted reconciliation identifiers, integer amounts/timestamps, supported status values, INR and capture booleans. Card metadata, payer contact details, notes, banking credentials and unknown fields are discarded. HMAC authentication and duplicate/body-conflict checks still use the original bytes and their SHA-256 digest. Historical receipts are preserved without rewriting existing data.
- Handover requires verified captured status and the appropriate funded booking state. Dismissing an unpaid checkout sends no verification request and creates no funding journal. A genuine provider capture can still arrive after a browser closes; dismissal does not cancel a payment already accepted by the provider.
- Escrow journals and lender allocations remain explicitly simulated. Test refunds retain existing human authorization, intent integrity and provider reconciliation checks. No application endpoint performs real payouts or marketplace transfers.

## Webhook and runtime preservation

The full API remains loopback-only on port 8001. The separate port-8010 proxy accepts only the exact webhook POST and preserves original-body HMAC validation, size/deadline limits, header stripping, deduplication and payload-conflict rejection. The tunnel continues targeting that proxy, not the full backend.

`run_test_webhook_stack.py --reuse-isolated-state` supports a controlled restart against the exact previously recorded isolated database without schema creation or migrations. The existing database, prepared unpaid booking and credential files are preserved. Other backend instances and the user-owned Cloudflare/React processes are not restarted by that operation. Other already-running deployments must reload the changed code before claiming these new guards.

No checkout, capture, refund, payout or external Razorpay mutation is used to validate this change. Regression tests shadow local gateway credentials and forbid real gateway network transport. Synthetic provider responses and newly generated test databases exercise payment state changes. Public runtime checks use denied GET routes and an invalid signature only; no signed synthetic receipt is added to the preserved database.

## Verification

Verification completed on **11 November 2026 (India time)**. Evidence is retained under `backend/.payment-verification/sandbox-only-20261110/`, named when the work began.

| Verification | Result |
| --- | --- |
| Complete backend regression suite after the final receipt-minimization change | **PASS: 266 passed, 3 skipped** in 195.92 seconds. The skipped tests require a dedicated PostgreSQL test service. |
| Frontend payment and photo tests | **PASS: 30 passed**, including missing/false sandbox flags, live keys, callback tampering, duplicate dialogs, dismissal and callback-field minimization. |
| Vite production build | **PASS**. The official hosted checkout loader is preserved. |
| Selected backend Ruff lint and format checks | **PASS**. Eight payment/provider/ingress/launcher/test files are formatted; configuration lint also passes. |
| Startup matrix | **PASS**: disabled without keys, explicit local mock and Test configuration start offline; live keys, unknown modes, partial credentials and conflicting modes are rejected. |
| Active isolated API/React | **PASS**: normal borrower login through port 5175 reaches the unchanged 100-paise booking on 8001; backend confirms sandbox-only operation and handover remains locked. |
| Active local/public webhook ingress | **PASS**: non-webhook routes remain 404; public invalid HMAC returns 400; public-host spoofing to the private API remains 403. Valid signatures, exact-byte tampering, deduplication, conflicts, limits and seven event handlers are covered by offline regressions. |
| Database and credentials | **PASS**: the same database was reused without migrations; hashes of every existing isolated table's rows and credential files remain unchanged. Counts remain two fixture users, one booking, one order transaction, four prior webhook receipts, zero funding journals and zero refund intents. |

Only the validated owned API/proxy processes were restarted to load the final code. Ports 8001, 8010 and 5175 remain available; the user-owned Cloudflare and React processes were preserved. No external Razorpay request, checkout, capture, refund, deduction, signed public synthetic delivery, EP integration, Git commit or push occurred during hardening.

The first targeted run exposed an authorization-order inconsistency and incorrect new-test expectations, which were corrected. The initial broad run found two synthetic concurrency adapters missing the new sandbox contract; those adapters now delegate to the guarded mock provider. The final full suite above passed without removing safety checks. Receipt minimization separately passed all 138 targeted checks before the final full rerun. Detailed results are in `backend-release.xml`, `active-runtime.json` and `runtime-preservation.json`.

The backend test command uses `.test-tools` on `PYTHONPATH`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, and fresh test output paths. The test conftest always creates a generated database and shadows real Razorpay credentials. Reproduce from `backend/`:

```powershell
New-Item -ItemType Directory -Force .payment-verification/sandbox-only-recheck | Out-Null
$env:PYTHONPATH = '.test-tools;.'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
python -B -m pytest tests -q --tb=short -rs --basetemp=.payment-verification/sandbox-only-recheck/tmp -o cache_dir=.payment-verification/sandbox-only-recheck/cache
```

Frontend verification uses the existing payment/photo test runner and Vite build (`npm test`, `npm run build`). No secrets or banking data are passed to either command.

## Limits

These checks establish the guards in the tested application paths and restarted isolated stack. They depend on Razorpay honoring Test-key namespace isolation and on the integrity of the server, browser and TLS trust. They do not certify arbitrary replacement code, infrastructure compromise or every deployed copy. PostgreSQL-specific behavior requires a dedicated test service. Genuine checkout, provider capture and Dashboard-originated delivery remain outside this task's permitted verification.
