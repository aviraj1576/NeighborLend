# NeighborLend - Agent Instructions

## Payment Safety and Current Verification
- Payments are strictly test-only. Default `PAYMENT_PROVIDER=disabled` starts without gateway keys.
- `mock` requires `PAYMENT_DEMO_MODE=true` and direct local loopback exposure; public mock is rejected.
- Every backend environment requires a privately generated strong `JWT_SECRET`; there is no fallback or test-mode bypass. Public deployments also require `DEPLOYMENT_EXPOSURE=public`.
- JWT configuration: `.env.example`; offline private-key check: `python -B scripts/verify_jwt_configuration.py`. Never print keys or tokens.
- `AUTO_MIGRATE=false` is the default. Importing the backend no longer creates/migrates schema.
- Never migrate or reset an existing application DB for tests. Tests initialize generated isolated DBs explicitly.
- Backend verification: `python -B scripts/verify_payments.py` from `backend/`.
- Frontend verification: `npm test` and `npm run build` from `frontend/`.
- Current implementation/setup/results: `docs/payment-system-verification.md`.
- Schema and verification: `docs/payment-architecture.md`, `docs/listing-negotiation-isolation-20261112.md` and `docs/handover-publication-20261112.md`. Private operational reports remain excluded from Git.
- Shared Supabase financial migration version 3 is applied. Do not rerun the initial hosted-apply wrapper or mutate existing financial records for tests. Future shared schema changes require explicit approval.

## Repository Structure
- **Monorepo**: `frontend/` (React 18 + Vite 8) + `backend/` (FastAPI + Python 3.11)
- **Root config**: `.env` (shared), `compose.yaml`, `render.yaml`, `vercel.json`
- **AI model**: `backend/ai_service/best_model.pt` (YOLOv8 for object detection)

## Development Modes

### Mode A: Frontend-Only (Recommended)
```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxied to deployed backend
```
- Uses `VITE_API_BASE_URL=https://neighborlend-6z0f.onrender.com/api` from `.env`
- No Python/PostgreSQL needed

### Mode B: Full Local Stack
```bash
# Backend (terminal 1)
cd backend
python -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Frontend (terminal 2)
cd frontend
npm install
npm run dev          # Proxies /api and /uploads to localhost:8000
```

### Docker (Production-like)
```bash
docker compose up --build   # Requires .env with DATABASE_URL, JWT_SECRET
```

## Key Commands

| Task | Command |
|------|---------|
| Frontend dev | `cd frontend && npm run dev` |
| Frontend build | `cd frontend && npm run build` (runs `check-web-env.mjs` first) |
| Frontend preview | `cd frontend && npm run preview` |
| Backend dev | `cd backend && python -m uvicorn app.main:app --reload` |
| Backend tests | `cd backend && python -m pytest` |
| Backend tests (verbose) | `cd backend && python -m pytest -v` |
| Lint/typecheck | None configured (add if needed) |

## Environment Variables (`.env` at root)
- **Frontend reads**: `VITE_API_BASE_URL`, `VITE_GOOGLE_CLIENT_ID` (via `vite.config.js` `envDir: '..'`)
- **Backend reads**: `pydantic-settings` loads absolute project-root `.env`, then `backend/.env`; process variables take precedence. Keep secrets out of `VITE_` variables.
- **Critical for local backend**: `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS`
- **Production backend**: `DATABASE_URL` (PostgreSQL), private `JWT_SECRET` (32+ bytes, 12+ distinct characters, no whitespace/defaults), `SUPABASE_*`, `SMTP_*`, `GOOGLE_CLIENT_ID`

## Testing
- **Backend**: `pytest` with isolated SQLite DBs; optional dedicated local PostgreSQL via `PAYMENT_TEST_POSTGRES_URL` (see `backend/tests/conftest.py`)
- **Frontend**: Node tests via `npm test`, including payment contracts and photo URL utilities
- Run tests from `backend/` directory

## Architecture Notes
- **Backend entrypoint**: `backend/app/main.py` — validates provider/exposure at startup; schema preparation is explicit unless `AUTO_MIGRATE=true`; mounts public listing uploads separately from private rental evidence
- **API routes**: `/api/auth`, `/api/listings`, `/api/borrow-requests`, `/api/chat`, `/api/ai`, `/api/uploads`, `/api/notifications`
- **Health check**: `GET /api/health` — verifies DB connectivity
- **CORS**: Configured via `CORS_ORIGINS` env var; must include frontend origin
- **Auth**: JWT (HS256) in Authorization header; Axios interceptor in `frontend/src/api/client.js`
- **AI inference**: Runs on photo upload via `uploads.py` router → `storage_service.py` → YOLOv8
- **Database**: SQLAlchemy 2.0; financial history is maintained by `migrate_payments` / `payment_schema_versions`, with reviewed SQL in `backend/migrations/payments/`. Alembic is installed but inactive. Startup does not migrate by default.

## Deployment
- **Frontend**: Vercel (root: `frontend/`, framework: Vite). Requires `VITE_API_BASE_URL` (HTTPS, path ends in `/api`)
- **Backend**: Render via `render.yaml` (Docker). Health check: `/api/health`
- **Supabase**: PostgreSQL + Storage bucket `listing_photos`
- **Email**: Brevo SMTP for OTP verification

## Common Gotchas
1. **CORS errors**: Ensure `CORS_ORIGINS` in `.env` includes your frontend origin (e.g., `http://localhost:5173`)
2. **JWT_SECRET**: Required in every environment; invalid/missing keys abort configuration before startup. Tests inject a fresh generated isolated key. HS256 is fixed; key rotation requires restarting backend processes and signing in again.
3. **Database**: Local default is SQLite (`sqlite:///./neighborlend.db`); production requires PostgreSQL
4. **AI model path**: `AI_MODEL_PATH` resolves relative to `backend/app/` parent dir
5. **Uploads**: Local dev uses `./uploads`; production uses Supabase Storage (requires `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`)
6. **Vite proxy**: Only works in dev; production frontend calls API directly via `VITE_API_BASE_URL`
7. **Build check**: `npm run build:web` validates `VITE_API_BASE_URL` is a public HTTPS URL ending in `/api`

## Git / PR Conventions
- Branch: `feature/your-feature-name` off `main`
- Commits: Conventional (`feat:`, `fix:`, `docs:`, etc.)
- PR checks: `npm run build` (frontend), `python -m pytest` (backend)
