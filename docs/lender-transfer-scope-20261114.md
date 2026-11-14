# Lender transfer support — requested scope, 14 November 2026

The user requested that actual lender transfer/payout support also be scoped while correcting the drill refund incident. **No transfer or payout implementation is enabled by the refund correction.** Current lender earnings remain simulated ledger allocations. The current Razorpay adapter still forbids transfer/payout endpoints, and no lender destination, product configuration, secret, or hosted schema was changed.

## Intended money flow

For the example successful rental, capture ₹580, authorize/refund ₹400 to the borrower, and allocate ₹180 rent to the lender subject to an explicitly agreed fee/payout policy. Only after the return/dispute decision, confirmed deposit refund, and whole-payment reconciliation should a separate server-authorized lender transfer be eligible. An unexplained additional refund, failed provider verification, insufficient balance, dispute, unknown transfer outcome, or missing/changed lender destination must block dispatch.

**A refund cannot be used to pay rent to a lender.** Its recipient is the original payment source. Route transfers and lender bank settlement require separate recipient/product support; transfer creation, provider processing and bank settlement must be presented as different states.

## Proposed provider integration

Razorpay Route is a suitable product to investigate for splitting a captured payment to an onboarded lender Linked Account. Razorpay's [Route integration guide](https://razorpay.com/docs/payments/route/integration-guide/) describes this account/destination setup. This is a proposed fit, not confirmation that this merchant is entitled to use it.

The proposed dispatch is a separate `POST /v1/payments/{payment_id}/transfers` operation using a server-selected Linked Account and the authorized lender amount, following the [transfer-from-payment API](https://razorpay.com/docs/api/payments/route/create-transfers-payments/). Inspect outcomes using the [GET transfers-for-payment API](https://razorpay.com/docs/api/payments/route/fetch-transfers-payment/) and individual transfer/settlement reads. Do not assume refund idempotency headers apply to transfers; choose an explicitly documented idempotent transfer operation or persist and reconcile an uncertain outcome before any retry.

A diagnostic GET for transfers attached to the incident payment returned **HTTP 400 / BAD_REQUEST_ERROR**, with a “not found” classification. It did not expose a transfer inventory. This does **not** prove that Route is enabled or disabled, or that a transfer exists/does not exist. Product entitlement and permitted test-account API behavior remain unverified. No new keys, onboarding calls, account creation, activation, transfer, reversal or payout were attempted.

## Required work before implementation and dispatch

1. Confirm the merchant's Route Test Mode entitlement and supported payment-to-transfer workflow, then establish verified Test Linked Accounts for the intended lenders. A client-supplied bank account or recipient ID must never select the destination at dispatch time.
2. Agree the fee policy: whether ₹180 is gross rent or lender net, who bears gateway fees/taxes/transfer charges/platform commission, what happens after an external refund, and when earnings become available. Provider fees cannot silently become a deposit deduction or be paid twice.
3. Review an additive schema design for lender-to-provider account mapping, immutable transfer authorization, operation/attempt history and provider reconciliation. Existing tables have no durable lender payout destination or transfer-intent model. Actual support therefore needs a separately reviewed migration; none is included or applied now.
4. Introduce a separately configured, default-disabled Test transfer provider with a narrow allowlist. Preserve the existing test-only key validation and refund service boundaries. Do not add generic arbitrary-URL dispatch or widen the current adapter as a shortcut.
5. Authorize one transfer allocation per booking/version using current accepted terms, admin policy, verified refund totals, lender ownership and provider funds availability. Snapshot the verified destination and amount. Commit authorization/attempt identity before external dispatch, avoid network calls under database locks, and fail closed after uncertain outcomes.
6. Use append-only transfer journals/events. A transfer reduces an authorized lender payable once; a refund to the borrower never clears a lender payable by pretending it was paid. Audit and reconciliation must distinguish transfers, reversals and actual bank settlement.
7. Add borrower/lender/admin UI showing deposit refund separately from lender transfer and settlement. Show “recorded”, “authorized”, “sent”, “provider processed”, “bank settled”, “failed”, and “unknown” only when corresponding authoritative evidence exists. Retain simulated labels until the new mode is explicitly configured and verified.

## Acceptance tests and approval boundary

First use isolated databases and synthetic provider transport for exact ₹580/₹400/₹180 allocation, fee policy, wrong lender/destination, missing entitlement, failed/unknown transfer, lost POST recovery, concurrent/duplicate dispatch, webhook signature/deduplication, refund-before-transfer, external-refund-after-authorization, reversal, and journal balance/immutability cases.

Then perform read-only product/destination validation. A new Razorpay Test payment or transfer, recipient onboarding, migration, refund, reversal, or hosted accounting adjustment still needs explicit approval with a concrete booking, destination and amount. A design request does not authorize those external operations. No live-mode support or automatic payout is implied.

The existing incident is already fully refunded according to the gateway. It is ineligible for an automatic ₹180 transfer from that payment. Choose an explicit, separately approved correction/funding plan after identifying the extra refund's origin; do not charge the borrower again or retry a refund to manufacture lender payment.

Evidence: `backend/.payment-verification/refund-incident-20261114/route-readonly.json`, `fixed-real-readonly.json`, and `docs/razorpay-refund-incident-20261114.md`.
