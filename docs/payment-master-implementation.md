# Payment integration — 11 November 2026

Completed on 12 November IST. See the [final verification report](payment-master-verification-20261112.md)
and [actual hosted Supabase table inventory](supabase-payment-tables.md).

## Architecture and implementation checklist

The existing FastAPI routers delegate financial transitions to `PaymentService`.
An accepted `negotiation_offers` row creates or associates a `borrow_requests` row
and exactly one `rental_bookings` commercial snapshot. The snapshot preserves
application varchar user IDs, accepted terms, integer paise and rental dates.
`payment_transactions` stores durable order operations and verified captures.
`refund_intents` and `refund_attempts` preserve authorized allocations and provider
recovery identities. `journal_transactions` and `escrow_ledger_entries` provide
balanced append-only accounting. `rental_disputes`, `financial_audit_records`,
`rental_evidence` and `processed_webhooks` already implement review, evidence,
audit and the durable webhook inbox. These are reused rather than replaced with
another payment or rental state machine.

The existing `payment_schema_versions` / `migrate_payments` mechanism is the
financial migration authority. Alembic is installed but has no migration history;
there is no Supabase CLI migration project. This implementation extends the
existing history, with reviewable SQL and a guarded deployment procedure.

The React payment card already connects checkout, reconciliation, return review,
claims, admin decisions and refund approval. Missing receipt downloads and explicit
checkout consent are integrated into that card. Existing ratings need stronger
backend settlement eligibility and visibility after resolved disputes.

- [x] Inspect existing providers, models, routers, workflow, tests and deployment.
- [x] Inspect configured hosted schema in a read-only transaction.
- [x] Extend additive financial protections and export reviewable SQL.
- [x] Validate migrations and concurrency on isolated PostgreSQL.
- [x] Integrate checkout consent and safe customer prefill.
- [x] Add authorized payment receipt and refund acknowledgment downloads.
- [x] Enforce settlement eligibility on existing ratings; preserve duplicate locks.
- [x] Install guards when creating new disposable webhook stacks.
- [x] Run backend, frontend, security and build regressions; review final diff.
- [x] Record evidence, hosted authorization and sandbox acceptance runbook.

The user subsequently authorized hosted table creation; the verified additive
migration was applied with a private backup and original-row preservation checks.
Fresh Razorpay financial operations still need separate approval. Historical
sandbox records are preserved. No live money movement or payout is supported.
