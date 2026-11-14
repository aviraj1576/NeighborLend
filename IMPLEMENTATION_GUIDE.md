# IMPLEMENTATION GUIDE — Damage Check Integration + Support Chatbot

Audience: an implementing model working phase by phase. Work through phases **in order**.
After each phase: run the phase's tests, tick the checklist, **stop and report** results
to the user. You may `/clear` context between phases — each phase is self-contained if
you re-read this file first.

**NEVER run `git add`, `git commit`, `git push`, `git stash`, `git branch`, or `git reset`.
The user commits manually.**

---

## Assumptions (defaults chosen where the spec was ambiguous)

1. **Repo root** = `d:\University\NeighborLend\NeighborLend` (the git repo). The damage
   module source lives OUTSIDE it at
   `d:\University\NeighborLend\damage_check_module\damage_check_module\damage_check\`
   and is **copied** into `backend/damage_check/` (Phase 1). The module's own frontend
   (`damage_check_frontend/`) is NOT copied; we build small React components in the main
   frontend and port one component (`BeforeAfterSlider.jsx`) from it.
2. **Damage photos are stored on local disk** under `backend/damage_data/` (NOT under
   `backend/uploads/` — that directory is statically served without auth). Check records
   go in a new DB table. Supabase storage for damage photos is out of scope (note for
   the user: photos are ephemeral on Render until a Supabase adapter is added).
3. **Link token**: `secrets.token_urlsafe(32)`, stored on the borrow request, expires
   **60 days after creation** (recomputed to `return_due_at + 30 days` once the rental
   starts, whichever is later). The same link is reusable by both parties until the lend
   closes or is resolved; after that it returns HTTP 410.
4. **Lender review timeout**: if the lender neither approves nor disputes within
   **72 hours** of return photo submission, the return is **auto-approved**. Applied
   lazily (checked on read/write of the handover), no cron job.
5. **Borrower never returns**: once the lend is **7 days past `return_due_at`** with no
   return submission, the **lender may raise a dispute without after photos**.
6. **Admin** = existing `users.is_admin` flag + existing `require_admin` dependency
   ([backend/app/services/auth.py:76](backend/app/services/auth.py#L76)). Admin logs in through the normal `/login`
   page. No public admin signup; the admin account comes only from the seed script.
7. **Support bot identity**: a seeded user with username `nl_support`
   (`support@neighborlend.local`). Support threads are ordinary `Conversation` rows with
   `lender_id = support_user.id`. A new `support_tickets` table tracks state/escalation.
8. **AI provider in dev/tests** = `DAMAGE_PROVIDER=mock` (module's offline mock). Real
   Gemini only when `DAMAGE_GEMINI_API_KEY` is set in `.env`.
9. **Legacy endpoints stay untouched**: the old `mark-given`/`confirm`/`return` endpoints
   and the duplicate `report-issue` registration in
   [backend/app/routers/borrow_requests.py](backend/app/routers/borrow_requests.py) are legacy; do NOT modify or delete
   them. (Note: `mark_handover_given` references a non-existent `HandoverStatus.marked_given`
   — it is already broken; leave it alone.) The new flow uses NEW endpoints only.
10. **No payment flow exists** in the codebase, so "payment" in the error-prone-steps
    list maps to the negotiation/offer step (where money is agreed).
11. **No UI skills** found in `.claude/skills` (only `settings.local.json` exists), so no
    skill invocation for frontend phases; match existing CSS patterns instead.
12. `handover_status` is a plain `String` column, so adding new status values needs no
    DB enum migration.

---

## Architecture overview

```
frontend (React 18 + Vite, plain CSS)          backend (FastAPI, SQLAlchemy, no Alembic)
  src/pages/BorrowRequestDetail.jsx  ──────▶   /api/borrow-requests/*  (lend lifecycle)
  src/pages/DamageCheckPage.jsx (NEW) ─────▶   /api/damage-links/{token} (NEW resolve)
  src/components/damage/* (NEW)      ──────▶   /api/damage-checks/*  (NEW: mounted module)
  src/pages/Admin*.jsx (NEW)         ──────▶   /api/admin/*          (NEW router)
  src/components/SupportChatButton   ──────▶   /api/support/*        (NEW router)
  src/pages/Chat.jsx (modified)      ──────▶   /api/conversations/*  (existing chat)
```

- The damage module is **mounted, not merged**: `backend/damage_check/` is vendored
  verbatim; the host provides a storage adapter + auth wrapper and mounts its router at
  `/api/damage-checks`. All *new business logic* (tokens, state transitions, disputes)
  lives in host routers, never inside `damage_check/`.
- One damage check per lend. The lend's 6 "before" photos ARE the damage check's before
  photos (the new flow replaces the old free-form `handover_photos` upload).
- The chatbot is pure data + if/else: a Python dict decision tree, keyword matching,
  quick-reply buttons carried in a new `meta` column on messages. Zero LLM calls.

### Key facts about the vendored module (read-only contract)

- Router endpoints (prefix `/api/damage-checks`): `POST ""` create; `GET /{id}` status;
  `PUT /{id}/photos/{phase}/{view}` upload (phase `before`=lender only, `after`=borrower
  only — enforced by the module); `GET /{id}/photos/{phase}/{view}` fetch;
  `POST /{id}/analyze` (202, idempotent, background task); `POST /{id}/decision`
  (lender: `confirmed`/`dismissed`).
- Views: `front, back, left, right, top, bottom`. Statuses: `collecting → processing →
  done | failed`. Report `overall`: `clear | possible_damage | needs_review`.
- `GET /{id}` returns `before_views`, `after_views`, `missing_before`, `missing_after`,
  `report`, `decision` — use these instead of tracking photo counts yourself.
- Module authorizes by participant user-id only. **Admin cannot use module endpoints**
  — admin photo access goes through the host admin router (Phase 4) using the storage
  adapter directly.
- `analyze` returns 409 while photos are missing (`DAMAGE_REQUIRE_ALL_VIEWS=true`
  default) — this is the "fewer than 6 photos" guard; surface its message in the UI.
- Photos uploads are rejected with 409 once analysis started ("double submission" guard).

---

## Reuse list (match these patterns; do not invent new ones)

| Need | Reuse | Where |
|---|---|---|
| Auth dependency | `get_current_user`, `require_admin` | [backend/app/services/auth.py](backend/app/services/auth.py) |
| Test JWTs | `create_access_token(user.id)` | same file |
| Notifications | `create_notification(db, user_id, type, title, message, link_url, borrow_request_id)` (caller commits) | [backend/app/services/notifications.py](backend/app/services/notifications.py) |
| System chat messages on a lend | `_record_handover_event(db, req, actor, content)` + `_handover_conversation_id(req)` | [backend/app/routers/borrow_requests.py:107-138](backend/app/routers/borrow_requests.py#L107-L138) |
| Lend lookup + party check | `_get_rental_participants(request_id, db, current_user)` (returns `(req, other_user_id)`, row-locked) | [backend/app/routers/borrow_requests.py:529](backend/app/routers/borrow_requests.py#L529) |
| Serialize a lend | `_format_request_out(req, include_private_handover=True)` | same file |
| Column migrations | `additions` dict in `migrate_schema()` | [backend/app/database.py:28](backend/app/database.py#L28) |
| DB sessions outside request scope | `SessionLocal()` from `app.database` | [backend/app/database.py](backend/app/database.py) |
| Backend test style | `unittest.TestCase` + `TestClient(app)` + direct ORM seeding + `create_access_token` headers | [backend/tests/test_handover.py](backend/tests/test_handover.py) |
| Frontend HTTP | `api` axios instance (adds Bearer token, 401 redirect) | [frontend/src/api/client.js](frontend/src/api/client.js) |
| Frontend photo URLs | `resolvePhotoUrl()` — wrap EVERY stored photo URL | [frontend/src/utils/photoUrl.js](frontend/src/utils/photoUrl.js) |
| File upload from browser | `FormData` + `api.post('/upload', form)` pattern | [frontend/src/pages/BorrowRequestDetail.jsx:120-140](frontend/src/pages/BorrowRequestDetail.jsx#L120-L140) (but damage photos go to the MODULE endpoint instead) |
| Page styling | One `Page.css` per page, tokens from `src/design/theme.css`, primitives in `src/components/ui/` | e.g. [frontend/src/pages/Inbox.css](frontend/src/pages/Inbox.css) |
| Route guard | `ProtectedRoute` in [frontend/src/App.jsx:20](frontend/src/App.jsx#L20) — copy its shape for `AdminRoute` |
| Before/after slider UI | Port `BeforeAfterSlider.jsx` from `..\..\damage_check_module\damage_check_module\damage_check_frontend\src\components\` | copy into `frontend/src/components/damage/` |

Commands (exact, from this repo):
- Backend tests: `cd backend` then `python -m pytest` (single file: `python -m pytest tests/test_damage_integration.py -v`)
- Backend dev server: `cd backend` then `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
- Frontend build check: `cd frontend` then `npm run build`
- Frontend dev server: `cd frontend` then `npm run dev` (port 5173, proxies `/api`)
- Seed: `cd backend` then `python seed_data.py` (**destructive**: drops all tables)

---

## Progress checklist (tick as you go)

- [x] Phase 0 — Seed data + env
- [x] Phase 1 — Vendor module + storage adapter + mount
- [x] Phase 2 — Data model + state machine + link tokens (backend)
- [ ] Phase 3 — Before/return/review/dispute endpoints (backend)
- [ ] Phase 4 — Admin backend: disputes, resolve, audit log, timeout
- [ ] Phase 5 — Frontend: before-photos flow + shareable link page
- [ ] Phase 6 — Frontend: return flow + lender review + dispute
- [ ] Phase 7 — Frontend: admin interface
- [ ] Phase 8 — Support bot backend
- [ ] Phase 9 — Support bot frontend + "Chat with us" buttons
- [ ] Phase 10 — Full regression + manual E2E script

---

## Lend status state machine (single source of truth)

All states live in `BorrowRequest.handover_status` (string). `*` marks NEW states.
Legacy states `not_applicable`, `issue_reported` and the legacy endpoints are unchanged.

| From | To | Trigger | Who | Endpoint |
|---|---|---|---|---|
| `pending` | `photos_uploaded` | 6 before photos complete, link generated + shared | Lender | `POST /api/borrow-requests/{id}/damage-check/share` |
| `photos_uploaded` | `borrower_confirmed` | Borrower confirms receipt (rental starts, `return_due_at` set) | Borrower | existing `POST .../handover/borrower-confirm` |
| `photos_uploaded`, `borrower_confirmed` | `issue_reported` | Borrower reports handover issue | Borrower | existing `POST .../handover/report-issue` |
| `borrower_confirmed` | `lender_confirmed` | Lender confirms handover complete | Lender | existing `POST .../handover/lender-confirm` |
| `lender_confirmed` | `return_photos_uploaded` | 6 after photos complete + analysis started (early return allowed any time before or on due date) | Borrower | `POST .../return/submit` |
| `return_photos_uploaded` | `return_confirmed` | Lender approves (lend → `closed`) | Lender | `POST .../return/approve` |
| `return_photos_uploaded` | `return_confirmed` | 72h timeout auto-approve (lazy) | System | applied inside GET/POST handover endpoints |
| `return_photos_uploaded` | `disputed` * | Lender raises dispute | Lender | `POST .../return/dispute` |
| `lender_confirmed` | `disputed` * | Lender disputes a non-return (only ≥7 days past `return_due_at`) | Lender | `POST .../return/dispute` |
| `disputed` * | `dispute_resolved` * | Admin decides (lend → `closed`) | Admin | `POST /api/admin/disputes/{id}/resolve` |

`BorrowRequest.status` becomes `closed` on `return_confirmed` and `dispute_resolved`.
Every transition endpoint must: (a) load the row with `with_for_update()` via the
existing helpers, (b) check the exact `from` state and return **409** otherwise (this is
the double-submission guard), (c) check the caller's role server-side, (d) write a
notification + a system chat message via the reuse helpers.

---

## Data model changes (reference; implemented in Phases 2, 4, 8)

All new tables are created automatically by `Base.metadata.create_all()`. New **columns
on existing tables** MUST also be added to the `additions` dict in `migrate_schema()`
([backend/app/database.py:31](backend/app/database.py#L31)) or deployed Postgres won't get them.

```python
# models.py — HandoverStatus: add two members
disputed = "disputed"
dispute_resolved = "dispute_resolved"

# models.py — BorrowRequest: add columns (+ migrate_schema additions["borrow_requests"])
damage_check_id = Column(String, nullable=True)            # "VARCHAR"
damage_link_token = Column(String, nullable=True, index=True)  # "VARCHAR"
damage_link_expires_at = Column(DateTime, nullable=True)   # "DATETIME"

# models.py — Message: add column (+ additions["messages"])
meta = Column(Text, nullable=True)   # "TEXT"  — JSON: {"quick_replies": [...], "node_id": "..."}

# models.py — NEW tables
class DamageCheckRecord(Base):          # host storage for the module's CheckRecord blob
    __tablename__ = "damage_check_records"
    check_id = Column(String, primary_key=True)
    record_json = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DisputeStatus(str, enum.Enum):
    open = "open"; resolved = "resolved"

class Dispute(Base):
    __tablename__ = "disputes"
    id = Column(String, primary_key=True, default=_uuid)
    borrow_request_id = Column(String, ForeignKey("borrow_requests.id"), nullable=False, index=True)
    check_id = Column(String, nullable=True)
    raised_by = Column(String, ForeignKey("users.id"), nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(Enum(DisputeStatus), default=DisputeStatus.open, index=True)
    outcome = Column(String, nullable=True)        # "lender" | "borrower" | "partial"
    resolution_note = Column(Text, nullable=True)
    resolved_by = Column(String, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"
    id = Column(String, primary_key=True, default=_uuid)
    admin_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String, nullable=False)        # e.g. "dispute_resolved", "support_reply"
    target_type = Column(String, nullable=False)   # "dispute" | "support_ticket" | "borrow_request"
    target_id = Column(String, nullable=False, index=True)
    detail = Column(Text, nullable=True)           # JSON string
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

class SupportTicketStatus(str, enum.Enum):
    bot = "bot"; escalated = "escalated"; closed = "closed"

class SupportTicket(Base):
    __tablename__ = "support_tickets"
    id = Column(String, primary_key=True, default=_uuid)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    context_step = Column(String, nullable=False)      # e.g. "handover_photos"
    entity_type = Column(String, nullable=True)        # "borrow_request" | "listing" | None
    entity_id = Column(String, nullable=True)
    status = Column(Enum(SupportTicketStatus), default=SupportTicketStatus.bot, index=True)
    escalated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

---

## New API surface (reference)

All endpoints require `Authorization: Bearer <jwt>` (existing `get_current_user`);
`/api/admin/*` additionally uses `require_admin`. Server-side role checks on EVERY
endpoint — never trust the client.

| Method & path | Who | Purpose |
|---|---|---|
| `POST /api/borrow-requests/{id}/damage-check/start` | Lender | Idempotently create the lend's damage check; returns `{check_id}` |
| `POST /api/borrow-requests/{id}/damage-check/share` | Lender | Verify 6 before photos, mint token, → `photos_uploaded`, message+notify borrower; returns `{link, token, expires_at}` |
| `GET /api/damage-links/{token}` | Lender/Borrower of that lend | Resolve link → `{borrow_request_id, check_id, role, handover_status, return_due_at}` (403 outsider, 404 unknown, 410 expired/closed) |
| `POST /api/borrow-requests/{id}/return/submit` | Borrower | Verify 6 after photos, start analysis, → `return_photos_uploaded`, set `returned_at`; works early ("Return today") |
| `POST /api/borrow-requests/{id}/return/approve` | Lender | → `return_confirmed`, lend `closed`, notify borrower |
| `POST /api/borrow-requests/{id}/return/dispute` `{reason}` | Lender | → `disputed`, create `Dispute`, notify borrower + all admins |
| `GET /api/admin/disputes?status=open` | Admin | List disputes (joined lend + party names + check status) |
| `GET /api/admin/disputes/{dispute_id}` | Admin | Full detail: dispute, lend, check record incl. AI report, photo URLs |
| `GET /api/admin/disputes/{dispute_id}/photos/{phase}/{view}` | Admin | Photo bytes via storage adapter (module endpoints won't serve admins) |
| `POST /api/admin/disputes/{dispute_id}/resolve` `{outcome, note}` | Admin | → `dispute_resolved`, lend `closed`, notify both, audit log |
| `GET /api/admin/audit-logs?limit=100` | Admin | Audit trail |
| `POST /api/support/chat` `{context_step, entity_type?, entity_id?}` | Any user | Create/reuse support conversation + ticket, bot greeting; returns `{conversation_id, ticket_id}` |
| `POST /api/support/conversations/{conversation_id}/messages` `{content}` | Ticket owner | Store user msg, run bot tree, store bot reply (with quick replies); returns both messages |
| `GET /api/admin/support/escalations` | Admin | List escalated tickets |
| `POST /api/admin/support/escalations/{ticket_id}/reply` `{content}` | Admin | Reply as support user, notify user, audit log |
| `POST /api/admin/support/escalations/{ticket_id}/close` | Admin | Close ticket, audit log |

The damage module adds (already implemented, just mounted): `POST /api/damage-checks`,
`GET /api/damage-checks/{id}`, `PUT/GET /api/damage-checks/{id}/photos/{phase}/{view}`,
`POST /api/damage-checks/{id}/analyze`, `POST /api/damage-checks/{id}/decision`.

---

# PHASES

## Phase 0 — Seed data + environment

> **Update (done):** the user tests directly on the hosted Supabase DB, so they use the
> non-destructive `backend/seed_test_users.py` (users `nl_test_admin`, `nl_test_lender`,
> `nl_test_borrower`, `nl_support`; log in by username; random passwords printed once;
> `--new-lend` creates a fresh pending lend). `seed_data.py` refuses to run on non-SQLite
> databases. Wherever this guide says "re-seed" or lists `alice`/`bob`/`admin` logins,
> use `seed_test_users.py --new-lend` and those usernames instead. Never run
> `seed_data.py` against the hosted DB.

**Goal**: seed script provides admin, lender, borrower, support user, and one sample
lend ready for handover; env has damage settings.

**Modify** [backend/seed_data.py](backend/seed_data.py):
- Keep existing users (alice=lender `alice@example.com`/`password123`, bob=borrower
  `bob@example.com`/`password123`, admin `admin@example.com`/`admin123` with
  `is_admin=True`, username `admin`).
- Add support user: `User(name="NeighborLend Support", username="nl_support",
  email="support@neighborlend.local", password_hash=hash_password(secrets.token_urlsafe(24)))`
  (random password — nobody logs in as it).
- Add a **sample accepted lend**: copy the setup pattern from
  [backend/tests/test_handover.py](backend/tests/test_handover.py) `_make_rental`: create a `Conversation`
  (borrower=bob, lender=alice), a `BorrowRequest` with `listing_id` of alice's
  "Power Drill", `max_price_per_day=150`, `needed_from=now+1d`, `needed_until=now+4d`,
  `status=open`, `handover_status="pending"`, and a `NegotiationOffer` with
  `status=OfferStatus.accepted`, `conversation_id`, `listing_id`, `borrow_request_id`
  linked. Print the created borrow_request id at the end.

**Modify** root `.env.example` (and tell the user to update `.env`): append
```
DAMAGE_PROVIDER=mock
# DAMAGE_GEMINI_API_KEY=
```

**Acceptance criteria**: `cd backend && python seed_data.py` prints the lend id without
errors; logging in as alice/bob/admin works against a running dev server.

**Tests**: none new. Run `cd backend && python -m pytest` to confirm nothing broke.
**Stop and report.**

---

## Phase 1 — Vendor the module, storage adapter, mount

**Goal**: `/api/damage-checks/*` works end to end with mock AI, backed by the main DB +
local disk.

**Create** `backend/damage_check/` — copy the entire folder
`d:\University\NeighborLend\damage_check_module\damage_check_module\damage_check\`
(files: `__init__.py, _compat.py, config.py, exceptions.py, images.py, prompts.py,
router.py, schemas.py, service.py, storage.py, providers/__init__.py,
providers/base.py, providers/gemini.py, providers/mock.py`). **Do not edit any of
these files, now or in later phases.**

**Create** `backend/app/services/damage_storage.py`:
```python
"""StorageBackend adapter: CheckRecord JSON -> damage_check_records table,
photo bytes -> local disk under backend/damage_data/ (never under uploads/,
which is publicly served)."""
from pathlib import Path
from damage_check._compat import dump_json, parse_json
from damage_check.schemas import CheckRecord
from damage_check.storage import LocalStorage
from app.database import SessionLocal
from app.models import DamageCheckRecord      # added in Phase 2; see note below

DAMAGE_DATA_DIR = Path(__file__).resolve().parents[2] / "damage_data"   # backend/damage_data

class HostDamageStorage:
    def __init__(self):
        self._photos = LocalStorage(DAMAGE_DATA_DIR)   # reuse module's photo file layout

    # --- record methods: one short-lived session per call (runs in worker threads) ---
    def save_check(self, record: CheckRecord) -> None:
        db = SessionLocal()
        try:
            row = db.get(DamageCheckRecord, record.id)
            if row is None:
                row = DamageCheckRecord(check_id=record.id)
                db.add(row)
            row.record_json = dump_json(record)
            db.commit()
        finally:
            db.close()

    def load_check(self, check_id):
        db = SessionLocal()
        try:
            row = db.get(DamageCheckRecord, check_id)
            return parse_json(CheckRecord, row.record_json) if row else None
        finally:
            db.close()

    # --- photo methods: delegate ---
    def save_photo(self, check_id, phase, view, data, mime): self._photos.save_photo(check_id, phase, view, data, mime)
    def load_photo(self, check_id, phase, view): return self._photos.load_photo(check_id, phase, view)
    def list_photos(self, check_id, phase): return self._photos.list_photos(check_id, phase)
```
Ordering note: `DamageCheckRecord` is defined in Phase 2. **In this phase, add just that
one model class** to [backend/app/models.py](backend/app/models.py) (it is a new table — no
`migrate_schema` entry needed).

**Create** `backend/app/services/damage_integration.py`:
```python
from functools import lru_cache
from fastapi import Depends
from damage_check import DamageCheckService, Settings as DamageSettings, provider_from_settings
from app.services.damage_storage import HostDamageStorage
from app.services.auth import get_current_user
from app.models import User

@lru_cache(maxsize=1)
def get_damage_service() -> DamageCheckService:
    settings = DamageSettings.from_env()
    return DamageCheckService(HostDamageStorage(), provider_from_settings(settings), settings)

def damage_user_id(user: User = Depends(get_current_user)) -> str:
    return str(user.id)
```

**Modify** [backend/app/main.py](backend/app/main.py): after the existing `include_router` calls add:
```python
from damage_check import create_router as create_damage_router
from app.services.damage_integration import get_damage_service, damage_user_id
app.include_router(create_damage_router(get_damage_service(), damage_user_id),
                   prefix="/api/damage-checks", tags=["Damage Check"])
```

**Add** `damage_data/` to [backend/.gitignore](backend/.gitignore) (create the file/line if needed).

**Tests** — **create** `backend/tests/test_damage_module_mount.py` following the
[test_handover.py](backend/tests/test_handover.py) pattern (`unittest.TestCase`, `TestClient(app)`,
ORM-seeded lender/borrower/intruder, `create_access_token` headers). At module top,
before importing `app`, set `os.environ.setdefault("DAMAGE_PROVIDER", "mock")`.
Generate a tiny valid image in-code:
```python
PNG_1PX = base64.b64decode(
 "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
```
Cases:
1. Lender `POST /api/damage-checks` with `{request_id, lender_id, borrower_id,
   item_class: "Drill"}` → 201, status `collecting`.
2. Lender uploads all 6 `before` views (`files={"file": ("a.png", PNG_1PX, "image/png")}`)
   → 200 each; `GET` shows `missing_before == []`.
3. Borrower upload to `before` phase → 403; intruder `GET` check → 403.
4. `POST /{id}/analyze` with missing after photos → 409 (fewer-than-6 guard).
5. Borrower uploads 6 `after` views, `analyze` → 202; poll `GET /{id}` until status
   `done` (loop ≤20 × `time.sleep(0.2)`); `report.overall` present.
6. Second `analyze` → 202 and does not reset the report (idempotent).

**Acceptance criteria**: `python -m pytest tests/test_damage_module_mount.py -v` green;
full `python -m pytest` green. **Stop and report.**

---

## Phase 2 — Data model, state machine values, link tokens (backend)

**Goal**: all schema changes in place; token mint/resolve endpoints work.

**Modify** [backend/app/models.py](backend/app/models.py): everything from the
"Data model changes" reference section EXCEPT `SupportTicket`/`SupportTicketStatus` and
the `Message.meta` column (those come in Phase 8): the two new `HandoverStatus` members,
the three `BorrowRequest` columns, `Dispute`, `DisputeStatus`, `AdminAuditLog`
(`DamageCheckRecord` exists from Phase 1).

**Modify** [backend/app/database.py](backend/app/database.py) `migrate_schema()` additions:
```python
"borrow_requests": { ...existing..., 
    "damage_check_id": "VARCHAR",
    "damage_link_token": "VARCHAR",
    "damage_link_expires_at": "DATETIME",
},
```

**Create** `backend/app/routers/lend_damage.py` with `router = APIRouter()`; **mount** in
[backend/app/main.py](backend/app/main.py): `app.include_router(lend_damage.router, prefix="/api",
tags=["Lend Damage"])`. Import and reuse `_get_handover_request`,
`_record_handover_event`, `_format_request_out` from `app.routers.borrow_requests`.

Endpoints in this phase:

`POST /api/borrow-requests/{request_id}/damage-check/start` (lender only):
```python
req, lender_id = _get_handover_request(request_id, db, current_user, lock=True)
# 403 if current_user.id != lender_id
# 409 unless req.handover_status == "pending" (or "photos_uploaded" and req.damage_check_id — idempotent re-entry)
if req.damage_check_id: return {"check_id": req.damage_check_id}   # idempotent
view = await service.create_check(current_user.id, req.id, lender_id, req.borrower_id,
                                  item_class=req.listing.category if req.listing else None)
req.damage_check_id = view.id; db.commit()
return {"check_id": view.id}
```
(Make the endpoint `async def` and get `service = Depends(get_damage_service)`.)

`POST /api/borrow-requests/{request_id}/damage-check/share` (lender only):
- 409 if no `damage_check_id`, or `handover_status` not in (`pending`, `photos_uploaded`).
- `check = await service.get_check(current_user.id, req.damage_check_id)`; 409 with
  detail `f"Missing before photos: {check.missing_before}"` if `check.missing_before`.
- Mint if absent (idempotent — re-sharing reuses the token):
  `req.damage_link_token = req.damage_link_token or secrets.token_urlsafe(32)`;
  `req.damage_link_expires_at = datetime.utcnow() + timedelta(days=60)`.
- Set `handover_status = "photos_uploaded"`; also set
  `req.handover_photos = json.dumps([])` is NOT needed — leave legacy columns alone.
- `link = f"/damage-check/{req.damage_link_token}"` (relative path; frontend origin-agnostic).
- `_record_handover_event(db, req, current_user, f"{current_user.name} uploaded 6 condition photos for {req.title}. Damage-check link: {link}")`
- `create_notification(db, req.borrower_id, "damage_check_link", "Condition photos ready",
  f"{current_user.name} documented {req.title}'s condition. Keep this link for the return.",
  link, req.id)`; `db.commit()`.
- Return `{"link": link, "token": req.damage_link_token, "expires_at": ..., "check_id": req.damage_check_id}`.

`GET /api/damage-links/{token}` (either party):
```python
req = db.query(BorrowRequest).filter(BorrowRequest.damage_link_token == token).first()
if req is None: raise HTTPException(404, "Unknown or revoked link")
lender_id = req.listing.owner_id if req.listing else None
if current_user.id not in (req.borrower_id, lender_id): raise HTTPException(403, "Not your lend")
if req.handover_status in ("return_confirmed", "dispute_resolved") or req.status == BorrowRequestStatus.closed:
    raise HTTPException(410, "This lend is closed")
if req.damage_link_expires_at and req.damage_link_expires_at < datetime.utcnow():
    raise HTTPException(410, "This link has expired")
return {"borrow_request_id": req.id, "check_id": req.damage_check_id,
        "role": "lender" if current_user.id == lender_id else "borrower",
        "handover_status": req.handover_status, "return_due_at": req.return_due_at}
```

Also **extend token lifetime at rental start**: in the EXISTING
`borrower_confirm_handover` ([backend/app/routers/borrow_requests.py:276](backend/app/routers/borrow_requests.py#L276)), after
`req.return_due_at` is set, add 3 lines: if `req.damage_link_expires_at` is set, set it
to `max(req.damage_link_expires_at, req.return_due_at + timedelta(days=30))`. This is
the only permitted edit inside an existing endpoint in this phase.

**Tests** — **create** `backend/tests/test_damage_links.py` (same TestCase pattern;
seed a lend with accepted offer exactly like `_make_rental` in test_handover.py):
1. `start` as borrower → 403; as lender → 200 with `check_id`; second call → same id.
2. `share` before photos uploaded → 409 mentioning missing views.
3. Upload 6 before photos via module, `share` → 200 with token; `handover_status ==
   "photos_uploaded"`; borrower has a notification with `link_url == f"/damage-check/{token}"`;
   a system message exists in the conversation.
4. `share` again → 200, same token (idempotent).
5. `GET /api/damage-links/{token}` as borrower → 200 role `borrower`; as intruder → 403;
   bad token → 404.
6. Expired: set `damage_link_expires_at = utcnow() - 1 day` directly in DB → 410.
7. Closed lend: set `handover_status = "return_confirmed"` → 410.

**Acceptance criteria**: new file green; full `python -m pytest` green. **Stop and report.**

---

## Phase 3 — Return, lender review, dispute (backend)

**Goal**: full new lifecycle `photos_uploaded → … → return_confirmed | disputed` works.

**Modify** `backend/app/routers/lend_damage.py` — add:

> **Circular-import warning (found in Phase 2):** `lend_damage.py` imports helpers from
> `borrow_requests.py` at module level. So when `get_handover` in `borrow_requests.py`
> needs `_apply_review_timeout`, import it INSIDE the function body
> (`from app.routers.lend_damage import _apply_review_timeout`), never at the top of the file.

Helper `def _apply_review_timeout(db, req) -> bool`:
```python
# Auto-approve if the lender sat on it for >72h. Call at the top of
# return/approve, return/dispute, and GET /{id}/handover (see below).
if (req.handover_status == "return_photos_uploaded" and req.returned_at
        and datetime.utcnow() - req.returned_at > timedelta(hours=72)):
    req.handover_status = HandoverStatus.return_confirmed.value
    req.return_confirmed_at = datetime.utcnow()
    req.return_confirmed_by = None   # system
    req.status = BorrowRequestStatus.closed
    create_notification(db, req.borrower_id, "return_confirmed", "Return auto-approved",
        f"The lender did not review the return of {req.title} within 72 hours; it was approved automatically.",
        f"/borrow-requests/{req.id}", req.id)
    lender_id = req.listing.owner_id if req.listing else None
    if lender_id:
        create_notification(db, lender_id, "return_confirmed", "Return auto-approved",
            f"You did not review the return of {req.title} within 72 hours; it was approved automatically.",
            f"/borrow-requests/{req.id}", req.id)
    db.commit(); return True
return False
```
Also call `_apply_review_timeout` inside the EXISTING `get_handover` endpoint
([backend/app/routers/borrow_requests.py:141](backend/app/routers/borrow_requests.py#L141)) just before formatting the
response (import it there; 3-line change — the second permitted legacy edit).

`POST /api/borrow-requests/{request_id}/return/submit` (borrower only, `async def`):
- `_get_handover_request(..., lock=True)`; 403 if not borrower.
- 409 unless `handover_status == "lender_confirmed"`. (Early return: no due-date check —
  "Return today" simply calls this before the due date. If already
  `return_photos_uploaded` → 409 "Return already submitted".)
- 409 if `req.damage_check_id is None` ("This lend has no damage check").
- `check = await service.get_check(current_user.id, req.damage_check_id)`; 409 with
  missing list if `check.missing_after`.
- Start analysis: `view, should_run = await service.start_analysis(current_user.id, req.damage_check_id)`;
  if `should_run`: `background.add_task(service.run_analysis, req.damage_check_id)`
  (take `background: BackgroundTasks` param).
- Set `handover_status = "return_photos_uploaded"`, `returned_at = utcnow()`.
- Notify lender (`"return_submitted"`, link `/borrow-requests/{req.id}`) + system message
  "`{name} submitted 6 return photos for {title}. AI comparison is running.`"; commit.
- Return `_format_request_out(req, include_private_handover=True)`.

`POST /api/borrow-requests/{request_id}/return/approve` (lender only):
- Lock; 403 if not lender; run `_apply_review_timeout` first — if it fired, return the
  formatted request (already approved).
- 409 unless `handover_status == "return_photos_uploaded"`.
- Optionally (best effort, in try/except) record the module decision:
  `await service.decide(current_user.id, req.damage_check_id, "dismissed", "Lender approved return")`
  — ignore `Conflict` if analysis isn't `done` yet.
- `handover_status = "return_confirmed"`, `return_confirmed_at/by`, `status = closed`;
  notify borrower; system message; commit; return formatted request.

`POST /api/borrow-requests/{request_id}/return/dispute` body `{"reason": str}` (lender only):
- Lock; 403 if not lender; `_apply_review_timeout` first (if fired → 409
  "Review window elapsed; the return was auto-approved").
- Allowed from: `return_photos_uploaded`; OR `lender_confirmed` when
  `req.return_due_at and utcnow() > req.return_due_at + timedelta(days=7)` (non-return
  dispute). Else 409.
- 409 if an open dispute exists:
  `db.query(Dispute).filter(borrow_request_id==req.id, status==DisputeStatus.open).first()`
  → "A dispute is already open for this lend" (dispute-raised-twice guard; also covers
  `handover_status == "disputed"`).
- Validate non-blank reason (422, match `report_dispute`'s style).
- Create `Dispute(borrow_request_id=req.id, check_id=req.damage_check_id,
  raised_by=current_user.id, reason=reason)`; `handover_status = "disputed"`,
  `disputed_at = utcnow()`, `dispute_description = reason`.
- Notify borrower (`"dispute"`); notify EVERY admin:
  `for (admin_id,) in db.query(User.id).filter(User.is_admin == True): create_notification(db, admin_id, "admin_dispute", "Dispute raised", f"...{req.title}...", f"/admin/disputes", req.id)`.
- System message in the conversation; commit; return formatted request.

**Tests** — **create** `backend/tests/test_return_dispute.py` (seed via ORM as before;
drive states by uploading photos through the module API with mock provider and polling
analyze where needed; it is also fine to shortcut earlier states by setting
`handover_status` directly in the DB):
1. `return/submit` before 6 after photos → 409 listing missing views.
2. Happy path: after 6+6 photos and `lender_confirmed` state, submit → 200, status
   `return_photos_uploaded`, `returned_at` set; lender notified; double submit → 409.
3. Early return: works when `return_due_at` is days away.
4. `approve` by borrower → 403; by lender → 200, `return_confirmed`,
   `BorrowRequest.status == closed`.
5. Timeout: set `returned_at = utcnow() - 73h`; `GET .../handover` as lender →
   response shows `return_confirmed` (auto-approve fired).
6. `dispute` from `return_photos_uploaded` → 200, `disputed`, one `Dispute` row open,
   admin notification exists; second dispute → 409.
7. Non-return dispute: state `lender_confirmed`, `return_due_at = utcnow() - 8 days` →
   dispute allowed; with `return_due_at` 2 days past → 409.

**Acceptance criteria**: file green; full suite green. **Stop and report.**

---

## Phase 4 — Admin backend: disputes, resolve, audit log

**Goal**: admins list/inspect/resolve disputes with full photo + AI-report access.

**Create** `backend/app/routers/admin.py`, **mount** in main.py:
`app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])`. Every endpoint:
`admin: User = Depends(require_admin)` (from `app.services.auth`).

Helper `def _audit(db, admin_id, action, target_type, target_id, detail: dict)`:
creates `AdminAuditLog(..., detail=json.dumps(detail))` (caller commits).

`GET /disputes?status=open|resolved|all` (default `open`): return list of
```json
{"id","borrow_request_id","title","reason","status","outcome","created_at",
 "raised_by_name","lender":{"id","name"},"borrower":{"id","name"},
 "check_id","check_status","report_overall","damage_link_token"}
```
(`check_status`/`report_overall` from loading the check record via
`HostDamageStorage().load_check(check_id)` — direct storage access, not the module API;
null-safe when `check_id` is None for non-return disputes.)

`GET /disputes/{dispute_id}`: everything above plus `resolution_note`, `resolved_at`,
`dispute.reason`, the lend's dates, and the full `report` dict (`record.report` via
`dump_json`/`.dict()`-compatible: build it as
`json.loads(dump_json(record))` and pick fields), plus
`before_views`/`after_views` from `storage.list_photos(check_id, phase)`, plus
`photo_url_template": "/api/admin/disputes/{id}/photos/{phase}/{view}"`.

`GET /disputes/{dispute_id}/photos/{phase}/{view}`: validate `phase in ("before","after")`
and `view in ("front","back","left","right","top","bottom")` (400 otherwise); load via
`HostDamageStorage().load_photo(check_id, phase, view)`; 404 if missing; return
`Response(content=data, media_type=mime, headers={"Cache-Control": "private, max-age=300"})`.

`POST /disputes/{dispute_id}/resolve` body `{"outcome": "lender"|"borrower"|"partial",
"note": str}` (note REQUIRED non-blank when outcome is `partial`, else optional):
- 404 unknown; 409 if `dispute.status == resolved` (double-resolve guard).
- Load the lend `with_for_update()`; set `dispute.status=resolved`, `outcome`,
  `resolution_note`, `resolved_by=admin.id`, `resolved_at=utcnow()`.
- Lend: `handover_status = "dispute_resolved"`, `status = closed`.
- Notifications to BOTH parties, outcome-specific text, e.g. lender-favored:
  to lender "Dispute resolved in your favor for {title}. {note}", to borrower
  "Dispute for {title} was resolved in the lender's favor. {note}"; `partial` →
  "resolved with a shared outcome". `link_url=f"/borrow-requests/{lend.id}"`.
- System message into the lend conversation (reuse `_record_handover_event` with the
  admin as actor).
- `_audit(db, admin.id, "dispute_resolved", "dispute", dispute.id,
  {"outcome": outcome, "note": note, "borrow_request_id": lend.id})`; commit.

`GET /audit-logs?limit=100` (cap 500): newest first, join admin name.

**Tests** — **create** `backend/tests/test_admin_disputes.py`:
1. Non-admin hits any `/api/admin/*` → 403; no token → 401.
2. Seed a disputed lend (set states directly + a `Dispute` row + a check with photos via
   storage adapter or module API). `GET /disputes` shows it; `status=resolved` filter empty.
3. `GET /disputes/{id}` includes report fields and both photo view lists.
4. Photo endpoint returns bytes with image mime; bad view name → 400.
5. `resolve` with `partial` and blank note → 422; with `outcome="lender"` → 200; lend is
   `dispute_resolved` + `closed`; two notifications exist (one per party); one
   `AdminAuditLog` row with action `dispute_resolved`; resolve again → 409.

**Acceptance criteria**: file green; full suite green. **Stop and report.**

---

## Phase 5 — Frontend: before-photos flow + link page

**Goal**: lender runs the 6-photo guided capture at handover; borrower receives and can
open the link page.

**Create** `frontend/src/components/damage/SixPhotoCapture.jsx` + `SixPhotoCapture.css`:
- Props: `{ checkId, phase, onComplete }` (`phase` = `"before"` or `"after"`).
- Renders 6 labeled slots in order `front, back, left, right, top, bottom` with short
  hints ("Front — stand ~1m away, whole item in frame"). Each slot: hidden
  `<input type="file" accept="image/*" capture="environment">` + thumbnail preview.
- On file pick: `const form = new FormData(); form.append('file', file);`
  `await api.put(`/damage-checks/${checkId}/photos/${phase}/${view}`, form);`
  mark slot done on 200; show `err.response?.data?.detail` inline on failure (size/type
  rejections come from the module).
- On mount: `GET /damage-checks/{checkId}` and pre-mark already-uploaded views (resume
  support) using `before_views`/`after_views` for the given phase.
- Progress line "4 of 6 photos"; call `onComplete()` when all 6 are up.
- Styling: plain CSS, tokens from `src/design/theme.css`, match card styles used in
  [frontend/src/pages/BorrowRequestDetail.css](frontend/src/pages/BorrowRequestDetail.css).

**Modify** [frontend/src/pages/BorrowRequestDetail.jsx](frontend/src/pages/BorrowRequestDetail.jsx):
- In the lender "Step 1" block (currently around line 363, the free-form
  `uploadHandoverPhotos` UI shown when `handover_status === 'pending'`): REPLACE the
  free-form uploader with the damage flow (keep the old function in the file; unused is
  fine — no refactors):
  1. Button "Start condition check" → `POST /borrow-requests/{id}/damage-check/start`,
     store `check_id` in state.
  2. Render `<SixPhotoCapture checkId={checkId} phase="before" onComplete={...}/>`.
  3. When complete, button "Share with borrower" →
     `POST /borrow-requests/{id}/damage-check/share` → show the returned `link` with a
     copy-to-clipboard button and the expiry date; then refetch the request (status
     becomes `photos_uploaded`).
- The GET handover response has no `damage_check_id` field yet — **add
  `"damage_check_id": req.damage_check_id` and `"damage_link_token": req.damage_link_token if include_private_handover else None`**
  to `_format_request_out` in
  [backend/app/routers/borrow_requests.py:62](backend/app/routers/borrow_requests.py#L62) (two keys; and add the two
  fields as `Optional[str] = None` to `BorrowRequestOut` in
  [backend/app/schemas/borrow_request.py](backend/app/schemas/borrow_request.py)). Use them so a lender returning to the
  page resumes instead of restarting.
- Borrower view in `photos_uploaded` state: show "The lender documented the item's
  condition — view photos" linking to `/damage-check/{damage_link_token}`, above the
  existing confirm-receipt button (which stays as is).

**Create** `frontend/src/pages/DamageCheckPage.jsx` + `.css`; **route** in
[frontend/src/App.jsx](frontend/src/App.jsx): `<Route path="/damage-check/:token" element={<ProtectedRoute><DamageCheckPage/></ProtectedRoute>} />`.
- On mount: `GET /api/damage-links/{token}` → `{borrow_request_id, check_id, role, handover_status}`;
  then `GET /damage-checks/{check_id}`.
- 404/403/410 → friendly full-page message ("This link is invalid / not yours / has
  expired or the lend is closed") with a button to `/my-borrow-requests`.
- Content by role/state:
  - Always: photo grid of uploaded views —
    `<img src={resolvePhotoUrl(`/api/damage-checks/${checkId}/photos/before/${view}`)}>`…
    **NOTE**: module photo GETs require the Bearer header, which `<img>` does not send.
    Fetch each photo with `api.get(url, {responseType:'blob'})` and `URL.createObjectURL`
    — write a tiny `frontend/src/components/damage/AuthImage.jsx` wrapper component that
    does this (props `{src, alt}`), and reuse it everywhere damage photos render.
  - `role === "borrower"` and `handover_status === "lender_confirmed"`: the return flow
    (Phase 6 fills this in; for now show "Return opens here on the return day").
  - Report present (`check.status === "done"`): render `report.overall` badge + per-view
    findings list (Phase 6 component).

**Acceptance criteria**: `cd frontend && npm run build` passes. Manual: with the dev
servers up and seeded data, as alice open the sample lend → start check → upload 6
images → share → as bob see the notification in `/inbox`, open the link page, see the 6
before photos.

**Tests**: `cd frontend && npm run build` (there is no frontend unit-test runner;
`node --test src/utils/photoUrl.test.js` must still pass). Backend full suite still
green (you touched `_format_request_out`). **Stop and report.**

---

## Phase 6 — Frontend: return flow, lender review, dispute

**Goal**: borrower submits return (incl. "Return today"); lender reviews before/after +
AI log, approves or disputes.

**Create** `frontend/src/components/damage/BeforeAfterCompare.jsx` + `.css`: port
`BeforeAfterSlider.jsx` from
`d:\University\NeighborLend\damage_check_module\damage_check_module\damage_check_frontend\src\components\BeforeAfterSlider.jsx`
(adapt: images come in as props `beforeSrc`/`afterSrc` already object-URLs from
`AuthImage`-style fetching; restyle with theme tokens). Add a view switcher (6 tabs).

**Create** `frontend/src/components/damage/DamageReportView.jsx`: props `{report}`.
Renders: overall badge (`clear` green / `possible_damage` red / `needs_review` amber),
the disclaimer string, and per-view rows: view name, `damage_detected`, `confidence`,
findings (`type`, `description`, `location`), `note`/`error`. This is the "AI-assisted
log" the spec asks for.

**Modify** `frontend/src/pages/DamageCheckPage.jsx` — borrower return step (when
`role==="borrower"` and `handover_status==="lender_confirmed"`):
- Banner: if today < `return_due_at`: "Due {date}. Returning early? You can submit now."
  with button **"Return today"**; if due or overdue: "Return due — upload your 6 return
  photos." Both reveal the same flow:
- `<SixPhotoCapture checkId={check_id} phase="after" onComplete={...}/>`, then button
  "Submit return" → `POST /api/borrow-requests/{borrow_request_id}/return/submit` →
  then poll `GET /damage-checks/{check_id}` every 2s until `status` is `done` or
  `failed` (max ~60s, then show "analysis still running — check back"); on `done` show
  `<DamageReportView/>`.
- `handover_status === "return_photos_uploaded"` and role borrower: read-only "waiting
  for lender review (auto-approves after 72h)".

**Modify** [frontend/src/pages/BorrowRequestDetail.jsx](frontend/src/pages/BorrowRequestDetail.jsx):
- Borrower, state `lender_confirmed`: REPLACE the old `uploadReturnPhotos` UI (around
  line 510) with: the auto-selected link — a prominent button "Open return check" →
  `/damage-check/{damage_link_token}` — plus a small "...or paste your damage-check
  link" text input: on paste/submit, extract the token (last path segment) and navigate
  to `/damage-check/{token}`. Plus the same "Return today" early-return copy.
- Lender, state `return_photos_uploaded`: review card: `<DamageReportView report/>`
  (fetch check via `GET /damage-checks/{damage_check_id}`), `<BeforeAfterCompare/>`,
  and two actions: "Approve return" → `POST .../return/approve`; "Raise dispute" →
  textarea (required) + `POST .../return/dispute {reason}`; confirm dialog
  (`window.confirm`) before dispute. Refetch after either.
- Lender, state `lender_confirmed` and >7 days overdue (compute from `return_due_at`):
  show "Item not returned? Raise a dispute" with the same dispute textarea.
- State `disputed` (both roles): badge "Dispute open — NeighborLend admins are
  reviewing. You'll be notified of the decision."
- State `dispute_resolved`: badge "Dispute resolved — see your inbox for the decision."

**Acceptance criteria**: `npm run build` green. Manual happy path + dispute path work
end to end with mock provider (see Phase 10 script).

**Tests**: `npm run build`; backend suite still green. **Stop and report.**

---

## Phase 7 — Frontend: admin interface

**Goal**: admin logs in normally, opens `/admin/disputes`, resolves disputes.

**Modify** [frontend/src/App.jsx](frontend/src/App.jsx):
- Add `AdminRoute` next to `ProtectedRoute` (copy its shape; also require
  `user?.is_admin`, else `<Navigate to="/" />`). `AuthContext` already exposes the
  `/auth/me` user, which includes `is_admin`.
- Routes: `/admin` → `<Navigate to="/admin/disputes"/>`; `/admin/disputes` →
  `AdminDisputes`; `/admin/disputes/:disputeId` → `AdminDisputeDetail`; (Phase 9 adds
  `/admin/support`). All wrapped in `AdminRoute`.

**Modify** [frontend/src/components/Navbar.jsx](frontend/src/components/Navbar.jsx): if `user?.is_admin`, add an
"Admin" link to `/admin/disputes`. (Server still enforces everything; this is
convenience only.)

**Create** `frontend/src/pages/AdminDisputes.jsx` + `.css`: table of
`GET /api/admin/disputes?status=open` with a status filter toggle (open/resolved/all);
columns: lend title, parties, reason (truncated), AI overall, created_at; row → detail
page.

**Create** `frontend/src/pages/AdminDisputeDetail.jsx` + `.css`:
- `GET /api/admin/disputes/{id}`.
- Header: lend title, parties, dates, dispute reason, link token (read-only).
- **Side-by-side photos**: for each of the 6 views a row with before and after
  `AuthImage`s using `photo_url_template` (admin endpoints), or the
  `BeforeAfterCompare` slider per view — side-by-side grid is the required minimum.
- `<DamageReportView report/>` (reuse from Phase 6).
- Decision box (only when `status === "open"`): three radio options — "In favor of
  lender", "In favor of borrower", "Partial" — plus a note textarea (required for
  partial, label says so) → `POST /api/admin/disputes/{id}/resolve`; `window.confirm`
  first; on success show the resolved banner.
- When resolved: show outcome, note, resolver, timestamp.

**Acceptance criteria**: `npm run build` green. Manual: non-admin visiting `/admin/...`
is redirected; admin resolves a seeded dispute; both parties see inbox notifications;
lend shows `dispute_resolved`. **Stop and report.**

---

## Phase 8 — Support bot backend (rule-based, no LLM)

**Goal**: deterministic decision-tree bot over the existing chat tables + escalation.

**Modify** [backend/app/models.py](backend/app/models.py): add `Message.meta` column,
`SupportTicket`, `SupportTicketStatus` (see reference section). **Modify**
[backend/app/database.py](backend/app/database.py) additions: `"messages": {"meta": "TEXT"}`.

**Create** `backend/app/data/__init__.py` (empty) and `backend/app/data/support_tree.py`:
```python
# Decision tree as data. To add a node: add an entry + reference it from a parent's
# quick_replies. No code changes needed.
SUPPORT_TREE = {
  "root": {
    "message": "Hi! I'm the NeighborLend helper. What do you need help with?",
    "quick_replies": [
      {"label": "Photo upload problems", "next": "photos"},
      {"label": "Handover & condition check", "next": "handover"},
      {"label": "Returns & damage", "next": "returns"},
      {"label": "Offers & pricing", "next": "offers"},
      {"label": "Talk to a human", "next": "human"},
    ],
  },
  "photos": {
    "keywords": ["photo", "upload", "image", "camera", "blurry", "file"],
    "message": ("Photo tips: use JPEG/PNG/WebP under 8 MB. For the condition check you "
                "need all 6 views (front, back, left, right, top, bottom) — the upload "
                "button stays disabled until all 6 are in. If an upload fails, retry on "
                "a stronger connection."),
    "quick_replies": [{"label": "Still stuck", "next": "human"},
                      {"label": "Back to menu", "next": "root"}],
  },
  "handover": {
    "keywords": ["handover", "pickup", "condition", "before photos", "link", "confirm receipt"],
    "message": ("Handover: the lender takes 6 condition photos and shares a damage-check "
                "link; the borrower reviews them and taps 'Confirm receipt' — that starts "
                "the rental clock. Lost the link? It's in your Inbox notification and on "
                "the lend page."),
    "quick_replies": [{"label": "Link expired or broken", "next": "link_issue"},
                      {"label": "Back to menu", "next": "root"}],
  },
  "link_issue": {
    "keywords": ["expired", "410", "invalid link"],
    "message": ("If the link says expired or closed: the lend may already be completed. "
                "The lender can re-open the lend page and share again to reuse the same "
                "link while the lend is active. Otherwise, escalate below."),
    "quick_replies": [{"label": "Talk to a human", "next": "human"},
                      {"label": "Back to menu", "next": "root"}],
  },
  "returns": {
    "keywords": ["return", "damage", "dispute", "late", "overdue", "broke"],
    "message": ("Returns: open your damage-check link on the return day (or tap 'Return "
                "today' to return early), upload the 6 return photos and submit. The "
                "lender then has 72 hours to approve or dispute; silence auto-approves. "
                "Disputes go to NeighborLend admins with both photo sets."),
    "quick_replies": [{"label": "I disagree with a dispute", "next": "human"},
                      {"label": "Back to menu", "next": "root"}],
  },
  "offers": {
    "keywords": ["offer", "price", "counter", "payment", "cost", "deposit"],
    "message": ("Money is agreed in chat offers: open the conversation, tap the offer "
                "panel, set daily price and dates. Counters cancel the previous pending "
                "offer. The lender's minimum price is enforced automatically."),
    "quick_replies": [{"label": "Back to menu", "next": "root"},
                      {"label": "Talk to a human", "next": "human"}],
  },
  "human": {
    "escalate": True,
    "message": ("I've flagged this for the NeighborLend team — a human will reply here. "
                "Add any details below in the meantime."),
  },
}
FALLBACK_MESSAGE = ("Sorry, I didn't catch that. Pick an option below, or choose "
                    "'Talk to a human'.")
```

**Create** `backend/app/services/support_bot.py`:
```python
import json
from app.data.support_tree import SUPPORT_TREE, FALLBACK_MESSAGE

def resolve_node(text: str) -> tuple[str, dict]:
    """Deterministic resolution: exact quick-reply label match (case-insensitive,
    across ALL nodes) first; then keyword scan (node with most keyword hits wins,
    first-defined wins ties); else fallback -> root menu."""
    t = (text or "").strip().lower()
    for node_id, node in SUPPORT_TREE.items():
        for qr in node.get("quick_replies", []):
            if qr["label"].lower() == t:
                return qr["next"], SUPPORT_TREE[qr["next"]]
    best, best_hits = None, 0
    for node_id, node in SUPPORT_TREE.items():
        hits = sum(1 for kw in node.get("keywords", []) if kw in t)
        if hits > best_hits:
            best, best_hits = node_id, hits
    if best:
        return best, SUPPORT_TREE[best]
    return "fallback", {"message": FALLBACK_MESSAGE,
                        "quick_replies": SUPPORT_TREE["root"]["quick_replies"]}

def bot_message_fields(node_id: str, node: dict) -> dict:
    """content + meta for a Message row."""
    meta = {"node_id": node_id, "bot": True}
    if node.get("quick_replies"):
        meta["quick_replies"] = [qr["label"] for qr in node["quick_replies"]]
    return {"content": node["message"], "meta": json.dumps(meta)}
```

**Create** `backend/app/routers/support.py`, **mount**:
`app.include_router(support.router, prefix="/api/support", tags=["Support"])`.

Helper `def _get_support_user(db) -> User`: `db.query(User).filter(User.username ==
"nl_support").first()`; if missing, CREATE it on the fly (same fields as seed) so tests
and fresh DBs work without seeding.

`POST /chat` body `{"context_step": str, "entity_type": str|None, "entity_id": str|None}`:
- Find existing conversation (`borrower_id==current_user.id, lender_id==support.id`) or
  create one (copy the create shape from
  [backend/app/routers/chat.py:118-164](backend/app/routers/chat.py#L118-L164), but WITHOUT the notification to the
  support user).
- Create a `SupportTicket(conversation_id, user_id, context_step, entity_type, entity_id)`.
- Add a system `Message` (sender=support user, `is_system=True`):
  `f"Support request — step: {context_step}" + (f", ref: {entity_type} {entity_id}" if entity_id else "")`.
- Add the bot greeting: `Message(sender_id=support.id, is_system=False,
  **bot_message_fields("root", SUPPORT_TREE["root"]))`.
- Commit; return `{"conversation_id": conv.id, "ticket_id": ticket.id}`.

`POST /conversations/{conversation_id}/messages` body `{"content": str}`:
- 404 if conversation missing; 403 unless `current_user.id == conv.borrower_id` and
  `conv.lender_id == support.id` (i.e. it IS a support thread of this user).
- Store the user `Message` (non-blank check, 400 — match `send_message` style).
- Load the latest ticket for this conversation (newest `created_at`); if its status is
  `escalated`, store NO bot reply (humans are handling it) and return just the user
  message echo plus `{"escalated": true}`.
- Else `node_id, node = resolve_node(content)`; if `node.get("escalate")`: set ticket
  `status=escalated`, `escalated_at=utcnow()`; notify every admin
  (`"support_escalation"`, title "Support escalation",
  message f"{current_user.name} needs help at step {ticket.context_step}.",
  link `/admin/support`).
- Store bot `Message(sender_id=support.id, **bot_message_fields(node_id, node))`;
  commit; return `{"user_message": ..., "bot_message": ...}` using the chat router's
  `MessageOut` shape plus a `meta` field (add `meta: Optional[str] = None` to
  `MessageOut` in [backend/app/schemas/chat.py](backend/app/schemas/chat.py) and include it in
  `_format_message` in [backend/app/routers/chat.py:34](backend/app/routers/chat.py#L34) — that makes quick
  replies flow through the EXISTING conversation GET endpoints too).

**Extend** `backend/app/routers/admin.py`:
- `GET /support/escalations`: tickets with `status == escalated` (plus `?status=` filter
  like disputes), each with user name, context_step, entity ref, conversation_id,
  escalated_at, and the last user message preview.
- `POST /support/escalations/{ticket_id}/reply` `{"content": str}`: store a `Message` in
  the ticket's conversation with `sender_id = support_user.id` and
  `meta=json.dumps({"admin": True})`; notify the ticket's user
  (`"support_reply"`, link `/messages/{conversation_id}`); `_audit(db, admin.id,
  "support_reply", "support_ticket", ticket.id, {"length": len(content)})`; commit.
- `POST /support/escalations/{ticket_id}/close`: set status `closed`; audit
  (`"support_closed"`); bot farewell message optional — skip.

**Tests** — **create** `backend/tests/test_support_bot.py`:
1. Unit (no HTTP): `resolve_node("Photo upload problems")` → `photos`;
   `resolve_node("my PHOTO is blurry")` → `photos`; `resolve_node("zzz")` → fallback
   with root quick replies; `resolve_node("Talk to a human")` → `human` with
   `escalate` True.
2. `POST /api/support/chat` → 200; conversation exists with system msg + greeting
   carrying `meta` quick replies; calling again reuses the conversation but makes a new
   ticket.
3. Message round-trip: post "return" → bot reply node `returns`; the pair is also
   visible via existing `GET /api/conversations/{id}` (meta included).
4. Another user posting into that conversation → 403.
5. Escalation: post "Talk to a human" → ticket `escalated`, admin notification created;
   next user message gets NO bot reply.
6. Admin: list escalations shows it; reply → message stored as support user + user
   notification + audit row; close → status closed; non-admin → 403.

**Acceptance criteria**: file green; full backend suite green. **Stop and report.**

---

## Phase 9 — Support bot frontend + "Chat with us" everywhere

**Goal**: contextual "Chat with us" at every error-prone step; quick-reply buttons in
Chat; admin escalation view.

### Error-prone steps (identified from the code) — add the button at each

| # | Step | File / screen | context_step | entity |
|---|---|---|---|---|
| 1 | Listing photo upload + AI label mismatch | [frontend/src/pages/CreateListing.jsx](frontend/src/pages/CreateListing.jsx) (the `/upload` + detection step) | `listing_photos` | listing (id if editing, else null) |
| 2 | Listing form (pricing/category/location) | same page, near submit errors | `listing_create` | null |
| 3 | Offer / counter-offer (money step) | [frontend/src/pages/Chat.jsx](frontend/src/pages/Chat.jsx) offer panel | `negotiation` | borrow_request / listing id if present |
| 4 | Handover 6-photo condition check | [frontend/src/pages/BorrowRequestDetail.jsx](frontend/src/pages/BorrowRequestDetail.jsx) lender step | `handover_photos` | borrow_request id |
| 5 | Borrower confirm receipt | same page, borrower step | `handover_confirm` | borrow_request id |
| 6 | Return submission (6 after photos) | [frontend/src/pages/DamageCheckPage.jsx](frontend/src/pages/DamageCheckPage.jsx) + return step in BorrowRequestDetail | `return_flow` | borrow_request id |
| 7 | Dispute raise / dispute status | [frontend/src/pages/BorrowRequestDetail.jsx](frontend/src/pages/BorrowRequestDetail.jsx) review/dispute card | `dispute` | borrow_request id |
| 8 | Email OTP verification | [frontend/src/pages/VerifyEmail.jsx](frontend/src/pages/VerifyEmail.jsx) | `email_verify` | null |
| 9 | Damage-check link errors (404/410 page) | [frontend/src/pages/DamageCheckPage.jsx](frontend/src/pages/DamageCheckPage.jsx) error state | `damage_link` | null |

**Create** `frontend/src/components/SupportChatButton.jsx` + `.css`:
- Props: `{ step, entityType = null, entityId = null, label = "Chat with us" }`.
- Small unobtrusive button (life-ring emoji 🛟 + label). On click:
  `const res = await api.post('/support/chat', { context_step: step, entity_type: entityType, entity_id: entityId });`
  then `navigate(`/messages/${res.data.conversation_id}`)` (`useNavigate`).
- If the user is not authenticated (no token in localStorage), navigate to `/login`.
- Drop it into each location in the table above (one line per site; place near the
  step's error/action area; do not restructure the pages).

**Modify** [frontend/src/pages/Chat.jsx](frontend/src/pages/Chat.jsx):
- Parse `message.meta` (JSON, try/catch) when rendering. If `meta.quick_replies` and the
  message is the LAST message in the thread, render the labels as buttons under it;
  clicking sends that label as a normal outgoing message.
- Support-thread detection: `other_participant.username === 'nl_support'` → hide the
  offer/negotiation panel for that conversation, show a "NeighborLend Support" badge,
  and send messages via `api.post(`/support/conversations/${conversationId}/messages`,
  {content})` instead of the normal messages endpoint (the response contains the bot
  message — append both to local state). All other conversations behave exactly as
  before.
- Style `meta.admin` messages with a small "Staff" tag.

**Create** `frontend/src/pages/AdminSupport.jsx` + `.css`; route `/admin/support`
(AdminRoute) and a tab/link from `AdminDisputes`:
- List from `GET /api/admin/support/escalations`; selecting one loads the conversation
  via existing `GET /api/conversations/{id}`? **No** — admin is not a participant and
  would get 403. Instead add `GET /api/admin/support/escalations/{ticket_id}` to
  [backend/app/routers/admin.py](backend/app/routers/admin.py) returning the ticket + full message list
  (reuse `_format_message` from the chat router). Small backend addition in this phase;
  add a test case for it in `test_support_bot.py` (admin fetch → 200 with messages;
  non-admin → 403).
- Reply box → `POST /api/admin/support/escalations/{ticket_id}/reply`; Close button →
  `.../close`.

**Acceptance criteria**: `npm run build` green; backend suite green. Manual: from
CreateListing click "Chat with us" → lands in a support thread with the greeting +
buttons; "Talk to a human" escalates; admin sees it under `/admin/support`, replies;
user sees the staff reply in the same thread. **Stop and report.**

---

## Phase 10 — Regression + manual E2E script

Run everything:
1. `cd backend && python -m pytest` — all green.
2. `cd frontend && npm run build` — green. `node --test src/utils/photoUrl.test.js` — green.
3. `cd backend && python seed_data.py` then start both dev servers
   (`python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` and
   `npm run dev`).

### Manual E2E script (three browser profiles / incognito windows)

Accounts: lender `alice@example.com`/`password123`, borrower `bob@example.com`/`password123`,
admin `admin@example.com`/`admin123`. Use any 6 small JPG/PNG files.

**A. Happy path**
1. Alice → `/my-borrow-requests`? No — open the seeded lend: Alice → Inbox or navigate
   to `/borrow-requests/<seeded id>` (printed by seed). Start condition check → upload
   6 before photos → Share. Copy the shown link.
2. Bob → Inbox shows "Condition photos ready" → open link → sees 6 before photos. Back
   on the lend page → Confirm receipt (rental starts).
3. Alice → lend page → Confirm handover complete (`lender_confirmed`).
4. Bob → lend page → "Return today" (early return) → link page auto-opened → upload 6
   after photos → Submit return → wait for the mock analysis → report appears.
5. Alice → lend page → review card shows report + before/after compare → Approve
   return. Lend shows `return_confirmed` / closed; Bob gets a notification. Both can
   rate (existing feature still works).

**B. Dispute path**
6. Re-seed (`python seed_data.py`) and repeat steps 1–4, but at step 5 Alice chooses
   "Raise dispute" with a reason.
7. Lend shows `disputed` for both parties; Bob has a dispute notification; admin has an
   admin notification.
8. Admin → login → Navbar "Admin" → `/admin/disputes` → open the dispute → side-by-side
   photos + AI log visible → resolve "Partial" with a note.
9. Both Alice and Bob receive decision notifications; lend shows `dispute_resolved` and
   is closed; `/api/admin/audit-logs` (or the detail page) shows the action.

**C. Chatbot path**
10. Bob → `/create-listing` → click "Chat with us" → support thread opens with menu
    buttons → click "Photo upload problems" → canned answer; type "my return is late"
    → returns answer; click "Talk to a human" → escalation message.
11. Admin → `/admin/support` → sees the escalation with context step `listing_photos`
    → replies "We're on it" → Close.
12. Bob → `/messages` → support thread shows the Staff reply.

**D. Edge spot-checks**
13. Open Alice's damage link as admin (not a party) → 403 page. Mangle the token → 404
    page. After the lend closed (path A), open the link → 410 page.
14. During step 1, try Share after only 5 photos → inline 409 error naming the missing
    view.

Report the outcome of every lettered section to the user. **Done.**

---

## Do NOT

- Do NOT run any git write command (`add`, `commit`, `push`, `stash`, `branch`,
  `reset`). The user commits.
- Do NOT edit anything inside `backend/damage_check/` (vendored module).
- Do NOT touch the legacy endpoints (`mark-given`, `handover/confirm`, `/return`,
  `/dispute`, the duplicate `report-issue`) except the two 3-line additions explicitly
  called out in Phases 2–3, and the `_format_request_out`/schema additions in Phase 5.
- Do NOT refactor, rename, reformat or "clean up" unrelated code, even obviously dead
  code.
- Do NOT add dependencies. Backend needs none (the module uses stdlib + existing
  FastAPI/pydantic); frontend needs none.
- Do NOT serve damage photos from `/uploads` or any static mount; they must only flow
  through authenticated endpoints.
- Do NOT add a public admin signup or any client-only admin check; `require_admin` on
  the server is the gate.
- Do NOT call any LLM from the support bot.
- Do NOT skip the stop-and-report checkpoint at the end of each phase.
