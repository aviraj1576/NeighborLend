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

Nothing exists on Render/Vercel until you commit and push (I never run git). After you
push: Render rebuilds (the Dockerfile now copies `damage_check/`) and on startup creates
the new tables and columns in Supabase; then run the section B SQL once.
