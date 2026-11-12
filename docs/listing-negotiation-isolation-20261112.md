# Listing-scoped conversations

A conversation belongs to a borrower, lender and optional listing. The previous participant-only lookup reused the first item agreement when the same users opened another listing. The frontend now passes the clicked listing ID and the backend finds or creates that listing's thread.

## Contracts and preservation

- `POST /api/conversations` accepts `lender_id` and optional `listing_id`. The backend checks listing ownership and participant authorization.
- Scoped threads are unique on `(borrower_id, lender_id, listing_id)`. Creation and adoption are serialized; repeated clicks reuse the same thread.
- New offers, counters and acceptance cannot cross listing boundaries. Booking snapshots reject a request/offer listing mismatch or reuse with a different accepted offer.
- Conversation summaries identify the listing. React clears old offers and drafts on selection changes and ignores responses for another conversation.
- Unambiguous historical threads are adopted without moving messages or changing IDs. Mixed historical threads stay readable and unassigned. Their next negotiation cannot switch items.
- Agreed terms remain attached to the original offer/request/booking. Payment eligibility and terms are backend-authoritative.

## Reviewed migration and startup protection

The existing reviewed artifact is `backend/supabase/migrations/20261112081704_listing_scoped_conversations.sql`.

SHA-256: `7614998cd2bf19c7aa51b921f3e0e14177b04d718fa1ae36615e1e1d7beea2f6`.

It adds the nullable listing foreign key, backfills only owner-matched, unambiguous offer history and creates the participant/listing unique index. Duplicate scoped threads abort the transaction for review. It does not merge threads or modify financial history. Windows checkouts preserve the artifact's LF bytes through `.gitattributes`.

The separately authorized hosted recovery committed on 12 November 2026 at 13:48:43 UTC. Independent checks confirmed all 11 conversation IDs, nine listing associations, two unassigned historical threads, the validated foreign key and valid unique index. The current publication task does not execute SQL or authorize another migration.

The legacy generic schema helper could remove `conversations.listing_id`. That destructive path has been removed. Both automatic startup initialization and direct `migrate_schema()` now reject hosted Supabase before opening a connection or invoking generic DDL, regardless of `AUTO_MIGRATE`. The guard recognizes direct/pooler hosts and libpq host overrides. Keep `AUTO_MIGRATE=false` for the hosted application. The explicit additive conversation helper remains available for reviewed workflows and isolated tests; SQLite and dedicated local PostgreSQL tests still work.

This guard cannot revoke owner credentials or repair a previously loaded legacy process. Stop old workers before maintenance. Never use generic initialization against the hosted project or infer a remote deployment from configuration files.

## Verification

The final backend suite passes 497 cases with isolated SQLite and dedicated loopback PostgreSQL schemas. Listing coverage includes independent camera/ladder agreements, separate borrowers, repeat/concurrent clicks, authorization, cross-listing rejection, preserved rental/payment/refund history and atomic migration rollback. The suite includes 41 hosted-initialization guard cases.

Six isolated real-browser checks cover owner/listing routing, correct offers/defaults on reopening, draft reset, late responses/submissions and private conversation failures. No hosted conversation is created by these checks. Current read-only hosted checks and the full handover verification are summarized in [handover publication verification](handover-publication-20261112.md). Private database snapshots, account credentials, evidence and operational execution reports remain outside Git.
