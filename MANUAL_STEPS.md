# Manual steps (things only a human can do)

Updated after each phase. The table is the roadmap for ALL phases; details follow.

| When | Where | What |
|---|---|---|
| Now (Phase 1) | Render | Set `DAMAGE_PROVIDER`, `DAMAGE_GEMINI_API_KEY` (section A) |
| Now (Phase 1) | Local `.env` | Add the two `DAMAGE_*` lines (section A) |
| After the new tables exist (Phases 1, 2, 4, 8 deployed) | Supabase SQL editor | Enable Row Level Security on the new tables (section B). Re-run after each deploy that adds tables; it is safe to repeat |
| Before running `seed_data.py` | Local | Never against your hosted DB (section C) |
| Phase 5 onward | Vercel | Nothing. No new frontend env vars are planned |
| Phases 2–10 | Render / Supabase | No further env vars or buckets planned. If a phase needs one, it will be added here |

## A. Damage check module (Phase 1)

**Render** (service `neighborlend-api`) → Environment:

| Key | Value |
|---|---|
| `DAMAGE_PROVIDER` | `gemini` |
| `DAMAGE_GEMINI_API_KEY` | key from https://aistudio.google.com/apikey (paid tier recommended: the free tier may use submitted photos to improve Google products) |
| `DAMAGE_GEMINI_MODEL` | optional. Default `gemini-3.5-flash`; confirm that id in AI Studio or set a model you have access to |

- Until the key is set the app still starts, but every damage analysis ends as
  `needs_review` (never "clear").
- **Photo storage warning:** damage photos are written to `/app/damage_data` inside the
  container. Render's filesystem is ephemeral, so photos vanish on every redeploy or
  restart (check records live in Postgres and survive). Options: attach a Render
  Persistent Disk (paid) mounted at `/app/damage_data`, or request a Supabase-backed
  storage adapter later. Fine for local dev and tests.
- Optional: add the same keys to `render.yaml` with `sync: false`. Not done automatically.

**Local `.env`**: add `DAMAGE_PROVIDER=mock` (and an empty `DAMAGE_GEMINI_API_KEY=`);
see `.env.example`.

## B. Supabase — enable Row Level Security on the new tables

Why: tables created by the backend land in Supabase's `public` schema, which Supabase
exposes through its REST API. With RLS off, anyone holding your project's public `anon`
key could read them (dispute reasons, AI damage reports, admin audit logs, support
chats). The backend is unaffected: it connects as the table owner through the pooler,
which bypasses RLS.

Where: Supabase dashboard → SQL Editor → New query → paste → Run. Do this after the
backend has started at least once against that database (tables are created at startup).

```sql
ALTER TABLE IF EXISTS public.damage_check_records ENABLE ROW LEVEL SECURITY;  -- Phase 1
ALTER TABLE IF EXISTS public.disputes             ENABLE ROW LEVEL SECURITY;  -- Phase 2
ALTER TABLE IF EXISTS public.admin_audit_logs     ENABLE ROW LEVEL SECURITY;  -- Phase 2
ALTER TABLE IF EXISTS public.support_tickets      ENABLE ROW LEVEL SECURITY;  -- Phase 8
```

Do NOT add any policies: no policy means the REST API sees nothing, which is what we want.
Verify: Dashboard → Table Editor → each table shows "RLS enabled".
(Your older tables such as `users` and `messages` were created before this work; check
whether RLS is enabled on them too, and enable it the same way if not. That is outside
this task, so it was not changed.)

**Buckets:** do NOT create any bucket. If damage photos later move to Supabase Storage,
create a **private** bucket (not `listing_photos`, which is public).

**New columns on existing tables** (Phases 2 and 8) need no SQL: `migrate_schema()` adds
them on backend startup.

## C. Test accounts on your hosted Supabase database (non-destructive)

`seed_data.py` DROPS ALL TABLES, so it is blocked on any non-SQLite database. For
testing directly on Supabase use the non-destructive script instead. It only creates
what is missing, never deletes, never touches existing users:

```bash
cd backend
python seed_test_users.py                 # uses DATABASE_URL from your root .env (Supabase)
python seed_test_users.py --new-lend      # extra fresh pending lend to repeat a test run
python seed_test_users.py --reset-passwords   # forgot a password
```

It creates users `nl_test_admin` (the only admin), `nl_test_lender`, `nl_test_borrower`
(log in with the USERNAME) plus `nl_support`, a **paused** listing "Test Power Drill"
(hidden from Browse) and one accepted lend. Passwords are random and printed once
(or set `SEED_ADMIN_PASSWORD`, `SEED_LENDER_PASSWORD`, `SEED_BORROWER_PASSWORD` first).
Save them in a password manager. Because this is your real database, the admin account
exists on the live site: use a strong password, and delete the test users when finished
testing (Supabase Table Editor → `users`; delete their related rows first if foreign
keys complain).

Automated tests (`python -m pytest`) never touch Supabase: `tests/conftest.py` forces a
temporary SQLite file.

Starting the backend with your normal `.env` (locally or on Render) talks to Supabase and
creates the new tables/columns there. That is additive and expected.

## D. Deploying so Supabase actually gets the new tables

Nothing exists on Render/Vercel until the code is on the branch Render/Vercel deploy from
(normally `main`). Work is pushed to `feature/damage-check-integration`; merge it into
`main` (GitHub pull request) when you want it live. After the merge: Render rebuilds (the
Dockerfile now copies `damage_check/`) and on startup creates the new tables and columns
in Supabase; then run the section B SQL once.

## E. Testing the backend (Phases 0-4) by hand against Supabase — no frontend needed yet

Start the API locally with your normal `.env` (this connects to Supabase):

```bash
cd backend
python seed_test_users.py          # once; note the printed passwords + the lend id
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Swagger (`/docs`) "Authorize" does not work here because login takes JSON, so use curl
(Git Bash). Replace `<...>` with your values; use any 6 JPG/PNG photos (<8 MB), e.g. `p.jpg`.

```bash
B=http://127.0.0.1:8000/api
tok() { curl -s $B/auth/login -H 'Content-Type: application/json' \
  -d "{\"username_or_email\":\"$1\",\"password\":\"$2\"}" | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])"; }
L=$(tok nl_test_lender '<lender pw>'); R=$(tok nl_test_borrower '<borrower pw>'); A=$(tok nl_test_admin '<admin pw>')
LEND=<lend id>
post() { curl -s -X POST "$B$2" -H "Authorization: Bearer $1" -H 'Content-Type: application/json' -d "$3"; echo; }
photos() { for v in front back left right top bottom; do \
  curl -s -X PUT "$B/damage-checks/$2/photos/$3/$v" -H "Authorization: Bearer $1" -F file=@p.jpg >/dev/null; done; }

# 1. Lender: start the check, upload the 6 BEFORE photos, share -> returns the link
CHECK=$(post $L /borrow-requests/$LEND/damage-check/start | python -c "import sys,json;print(json.load(sys.stdin)['check_id'])")
photos $L $CHECK before
post $L /borrow-requests/$LEND/damage-check/share            # note "token"
# 2. Borrower resolves the link; an outsider/other login would get 403
curl -s $B/damage-links/<token> -H "Authorization: Bearer $R"; echo
# 3. Handover: borrower confirms receipt, lender confirms handover
post $R /borrow-requests/$LEND/handover/borrower-confirm '{}'
post $L /borrow-requests/$LEND/handover/lender-confirm
# 4. Return (works any day before the due date = early return): 6 AFTER photos, submit
photos $R $CHECK after
post $R /borrow-requests/$LEND/return/submit
curl -s $B/damage-checks/$CHECK -H "Authorization: Bearer $L"; echo   # repeat until "status":"done" (AI report)
# 5a. Happy path:  lender approves
post $L /borrow-requests/$LEND/return/approve
# 5b. OR dispute path (use --new-lend for a fresh lend):
post $L /borrow-requests/$LEND/return/dispute '{"reason":"Scratch on the left side"}'
curl -s "$B/admin/disputes" -H "Authorization: Bearer $A"; echo      # note the dispute "id"
post $A /admin/disputes/<dispute id>/resolve '{"outcome":"partial","note":"Split the repair"}'
curl -s "$B/admin/audit-logs" -H "Authorization: Bearer $A"; echo
```

Expected: every step returns 200; wrong-role calls return 403; repeating a step returns
409; the lend ends `return_confirmed` (5a) or `dispute_resolved` (5b); both users get
notifications (`GET $B/notifications` with their token). With a real `DAMAGE_GEMINI_API_KEY`
the report is real; with identical test photos expect `clear`.

## F. Going live (after Phases 0-10) — checklist, in this order

1. **Merge** `feature/damage-check-integration` into `main` (GitHub pull request). Vercel and
   Render deploy from `main`.
2. **Render** env vars set (section A): `DAMAGE_PROVIDER=gemini`, `DAMAGE_GEMINI_API_KEY`.
   Nothing else new. Wait for the deploy to finish and `/api/health` to return ok.
3. **Supabase → SQL Editor**: run the section B SQL (it now covers `damage_check_records`,
   `disputes`, `admin_audit_logs`, `support_tickets`). The backend creates these tables on its
   first start, and adds the new `borrow_requests` / `messages` columns automatically.
4. **Create your real admin** on the live database. `seed_test_users.py` makes a test admin
   (`nl_test_admin`) from your laptop; use a strong `SEED_ADMIN_PASSWORD`, or promote your own
   account in the Supabase Table Editor (`users` → your row → `is_admin` = true). There is no
   public admin signup by design. Delete the test users when you are done testing.
5. **Vercel**: nothing new to set. The camera needs HTTPS, which Vercel provides.
6. Open the live site as the test lender/borrower and run the E2E script in section E / the
   guide's Phase 10.

Known limits to be aware of on the live site:
- Damage photos live on Render's ephemeral disk (see section A). Until you add a persistent disk
  (or a Supabase-backed store) photos disappear on redeploy, and a link to a lend whose photos
  were wiped shows "Photo unavailable".
- The AI comparison is only a warning, never a verdict, and needs a real Gemini key to be useful
  (`mock` reports every differing photo as a change).
- The email-verification step has no "Chat with us" button: users cannot sign in (so cannot open a
  support chat) until they are verified. The bot's "Email verification" topic is reachable from
  any other support chat.
