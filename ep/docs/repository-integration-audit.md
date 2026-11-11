# Read-only repository integration audit

Audited on 2026-11-08. Actual root: `D:/neighborlend_project/NeighborLend` (contains
`backend`, `frontend`, `docs`, `AGENTS.md`, `compose.yaml`, `README.md`). Workspace parent
is not the Git root. Initial Git status was clean. Root instructions were read; root
configuration, backend, frontend and models were left unchanged.

| Existing path | Observed entry points/contracts | Future EP interaction |
| --- | --- | --- |
| `backend/app/main.py` | FastAPI `app`; `/api/*` routers; `Base.metadata.create_all`, `migrate_schema`, upload-directory creation at import; YOLO preload on lifespan; public `/uploads` mount | Run EP separately; never import this module for EP initialization/tests |
| `backend/app/database.py` | SQLAlchemy engine from `get_settings`, `get_db`, `migrate_schema` additive schema changes | No reuse of engine or migrations; approved future linking only via rental IDs/API |
| `backend/app/routers/uploads.py` | `POST /api/upload`, `upload_file`, `get_current_user`; reads image bytes, optional detections, storage helper | Future private evidence upload should be a distinct flow |
| `backend/app/services/storage_service.py` | `save_upload`, `save_upload_from_bytes`, `delete_upload`; local `uploads` URLs or existing public `listing_photos` bucket; `_ensure_public_bucket` | Public listing storage is unsuitable for private inspection evidence; future private adapter/bucket must be separate |
| `backend/app/services/ml_service.py` | Lazy `_get_model`, `detect_objects`, Ultralytics YOLO, temporary JPEG, returns detections or empty list when unavailable | Object-category hints only, never physical identity/damage proof; no reuse in Phase 1 |
| `backend/app/services/ai_identifier.py` | `identify_item`, `_get_model`, category mapping, optional YOLO | Preserve existing behavior; no Phase 1 imports/model downloads |
| `backend/app/routers/ai.py` | `POST /api/ai/identify` → `identify_item` | Independent of future condition inspection |
| `backend/app/routers/chat.py` | `accept_offer`, `POST /api/offers/{offer_id}/accept`, records accepted offer, creates BorrowRequest with `handover_status=pending` | Proposed trusted integration establishes rental context after acceptance |
| `backend/app/services/negotiation.py` | Rental duration/cost and availability checks on accepted offers | Keep financial/availability logic outside EP |
| `backend/app/routers/borrow_requests.py` | `_get_handover_request` checks borrower/listing-owner; `/api/borrow-requests/{request_id}/handover/upload-photos` (`upload_handover_photos`), `/handover/borrower-confirm` (`borrower_confirm_handover`), `/handover/lender-confirm` (`lender_confirm_handover`) | Future before-evidence ingestion/acknowledgement; preserve original evidence and explicit capture stage |
| same file | `/return/upload-photos` (`upload_return_photos`), `/return/confirm` (`confirm_return`), `/return` (`report_return`), issue/dispute endpoints | Future after-evidence ingestion and inspection request before human return review; EP must not auto-confirm return |
| `backend/app/models.py` | User, Listing/ListingPhoto, BorrowRequest, NegotiationOffer, Conversation; BorrowRequest has borrower_id, listing_id, handover/return photo JSON text fields, confirmation/due/return/dispute timestamps | Rental ID is BorrowRequest.id; lender comes from Listing.owner_id, not arbitrary client role |
| `backend/app/services/auth.py` | `get_current_user`, OAuth2 Bearer; JWT subject/expiry via configured algorithm, database user existence + verified flag; `require_admin` | Future adapter verifies existing identity and current rental membership, without copying insecure defaults or importing startup side effects |
| `backend/app/schemas/borrow_request.py`, routers | Pydantic response/request schemas; HTTPException errors conventionally use `detail`; handover paths use 403/409/422 for access/state/input | Future backend adapter maps EP error envelopes to existing frontend convention |
| `backend/ai_service/test_damage_comparison.py` | Standalone CLI experiment with `google.genai`, image pair, structured Pydantic result, root/backend dotenv key lookup | Inspected as text only; never executed/imported; no paid calls; not an established benchmark or production comparison pipeline |
| `frontend/src/pages/BorrowRequestDetail.jsx` | Handover/return photo review and workflow requests | Future status/findings presentation requires separately approved frontend changes |
| `frontend/src/api/client.js` | Axios API client/auth header integration | Future backend-mediated access; no service credentials in browser |
| `compose.yaml`, `render.yaml`, `backend/Dockerfile`, `frontend/vite.config.js` | PostgreSQL-backed deployed backend, persistent local upload volume in Compose, Render health path `/api/health`, Vite proxy/deployed API | EP gets no deployment change in Phase 1; future private durable volumes/worker/service configuration need approval |
| `backend/requirements.txt` | FastAPI 0.115.0, Pydantic 2.13.5, Pillow 10.4.0, Ultralytics 8.4.174 and cloud/database packages pinned | Actual audited Conda versions differ; EP uses already available compatible packages, does not change root requirements |

`scripts/audit_repository.py` used `ast.parse` only on backend application Python files;
`docs/existing-syntax-audit.json` contains the actual result. No backend imports or
database calls occurred. Existing backend tests were inspected as context, not executed:
the EP validation boundary requires its own isolated data and test suite.
