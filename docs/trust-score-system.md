# NeighborLend Trust Score

Trust scores are displayed and stored from 0.00 to 5.00. The score combines a
Bayesian rating score (45%), transaction reliability (30%), transaction
experience (15%), and account verification (10%). Ratings use a fixed 3.5/5
prior with five prior reviews. Experience grows with completed rentals; open or
cancelled rentals are not counted. Open disputes are excluded until resolved.

Reliability follows the existing trust score prototype's five-rental prior:
`5 * (1 - (losses + 0.25 * neutral outcomes) / (completed rentals + 5))`,
clamped to 0–5. Dispute outcomes are role-specific: a full adjudicated deposit
deduction counts against the borrower; a rejected claim counts against the
lender; mutual/partial outcomes carry a quarter-weight penalty to both.

## Existing database

`AUTO_MIGRATE=false` remains the default. For a shared PostgreSQL database,
review and explicitly authorize `backend/migrations/trust/001_trust_score_components.sql`,
then run `python -B scripts/backfill_trust_scores.py --confirm-shared-database`
from `backend/` to rebuild the derived score cache from rentals, ratings and
resolved disputes. Do not run this command against production until the schema
change and data update have been reviewed. The breakdown lives in its own
additive table. Existing login and profile reads remain compatible before the
migration; trust endpoints calculate the breakdown live until the snapshot table
is available. Local/isolated databases receive the additive migration through
the existing explicit `migrate_schema()` workflow.

Trust score reads are authenticated at `/api/trust/me` and
`/api/trust/{user_id}`. Profile and listing summaries expose the cached
breakdown and update timestamp.
