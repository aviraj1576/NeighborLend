# Proposed future integration — no existing files changed

EP is an independent local service in Phase 1. The following are proposals requiring
separate authorization, not implemented changes to backend/frontend/deployment.

1. After `backend/app/routers/chat.py:accept_offer`, use the committed BorrowRequest ID
   as rental context. Resolve lender from the listing owner and borrower from the rental.
   Trigger only after a successful transaction; use idempotency/outbox handling in a
   future integration rather than coupling two databases in one HTTP transaction.
2. Replace local fixture authorization with an adapter that verifies NeighborLend's
   existing JWT issuer/algorithm/expiry, verified user and current rental participation.
   Recheck rental state and upload-stage permissions against trusted records; never accept
   a forwarded client identity header as proof. An alternative service-to-service adapter
   needs a documented authenticated delegation protocol, scopes and revocation behavior.
3. At `upload_handover_photos`, privately ingest immutable lender before-evidence and
   store opaque evidence IDs associated with the rental. Borrower confirmation should
   bind the acknowledged evidence manifest, not overwrite original bytes. At
   `upload_return_photos`, ingest borrower after-evidence using the same rental context.
4. Create an inspection after both authorized evidence sets are fixed. Do not perform
   expensive inference in rental HTTP handlers. A durable queue/worker may later claim
   queued jobs, track pipeline version/artifact provenance, recover leases after restarts,
   and atomically record validated reports before allowing completion.
5. Read status through authenticated backend endpoints. Proposed frontend changes in
   `frontend/src/pages/BorrowRequestDetail.jsx` should show pending/unavailable/failed,
   evidence citations, comparison limitations, inconclusive results, and explicit human
   review. Browser clients must never receive service credentials or private storage paths.
6. Preserve evidence, model/config versions, acknowledgements and report history for a
   separately defined dispute process. Reports are advisory; lenders review physical
   returns. EP cannot authorize deductions, liability, settlement or return confirmation.

A future private object-storage adapter should implement opaque-key write/read/delete,
SHA verification and health checks without public URLs. Use a dedicated **private**
bucket and server-verified membership; never reuse the existing public `listing_photos`
storage behavior. Provider-specific policies, credentials, signed-URL lifetimes and
recovery/transaction journal need design and security tests before adoption. Current
local recovery enumerates local files and must be replaced with adapter-specific recovery
for remote storage. No cloud storage/API configuration is accessed in Phase 1.

Potential approved files later: backend authentication/borrow-request integration,
new explicit evidence associations/migrations, frontend review UI, deployment service/
worker/private volume configuration. None of these changes are performed here. Existing
root CI, dependencies, `.env`, Compose, YOLO code and weights are unchanged.
