# V0 Foundations — Completion Report

**Date:** 2026-05-31 · **Phase:** V0 (foundations only) · **Next:** V1 Authentication (awaiting approval)

Scope built strictly per `V1_ARCHITECTURE_PACKAGE.md` + `api/openapi-v1.yaml`. **No** auth/employees/attendance/projects/reports/dashboard business logic. No AI, biometric, WhatsApp/SMS, multi-tenancy, microservices, Kubernetes, or deployment work.

---

## 1. Folder structure

```
coreops/
├── .gitignore                      # populated
├── .env.example                    # compose vars (ports, db creds)
├── docker-compose.yml              # wms project: db, redis, backend, worker, frontend
├── backend/
│   ├── Dockerfile  .dockerignore  .env.example  requirements.txt  pyproject.toml  README.md
│   ├── alembic.ini
│   ├── alembic/  env.py  script.py.mako  versions/.gitkeep
│   ├── app/
│   │   ├── main.py                 # app factory: CORS, error envelope, health router
│   │   ├── health.py               # /health, /health/ready
│   │   ├── core/  config.py  database.py  redis.py  celery_app.py  deps.py
│   │   ├── shared/ base.py  errors.py  pagination.py
│   │   └── modules/  (empty — one module per future phase)
│   └── tests/  conftest.py  test_health.py
└── frontend/
    ├── Dockerfile  .dockerignore  .env.local.example  package.json  tsconfig.json  next.config.js  README.md
    └── src/
        ├── app/  layout.tsx  page.tsx  globals.css
        └── lib/  api.ts  config.ts
```

## 2. Files created (42)

**Root (3):** `.gitignore`, `.env.example`, `docker-compose.yml`.
**Backend (24):** `Dockerfile`, `.dockerignore`, `.env.example`, `requirements.txt`, `pyproject.toml`, `README.md`, `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/.gitkeep`, `app/__init__.py`, `app/main.py`, `app/health.py`, `app/core/{__init__,config,database,redis,celery_app,deps}.py`, `app/shared/{__init__,base,errors,pagination}.py`, `app/modules/__init__.py`, `tests/{__init__,conftest,test_health}.py`.
**Frontend (12):** `package.json`, `tsconfig.json`, `next.config.js`, `Dockerfile`, `.dockerignore`, `.env.local.example`, `README.md`, `src/app/{layout.tsx,page.tsx,globals.css}`, `src/lib/{api.ts,config.ts}`.

## 3. What each layer does
- **Config** (`core/config.py`): pydantic-settings; all secrets/URLs/ports/`PRODUCT_NAME` from env, nothing hardcoded.
- **PostgreSQL** (`core/database.py`): SQLAlchemy 2.0 engine + `SessionLocal` + `Base` + `get_db` dependency.
- **Redis** (`core/redis.py`): shared client + `get_redis` (used by readiness now; JWT denylist in V1).
- **Celery** (`core/celery_app.py`): app declared on Redis broker; **no tasks** in V0.
- **Shared** (`shared/`): UUID/timestamp/soft-delete mixins, uniform error envelope (matches OpenAPI), pagination primitives.
- **Health** (`health.py`): `GET /api/v1/health` → `{"status":"ok"}` (exact OpenAPI contract); `GET /api/v1/health/ready` → DB+Redis probe (ops addition, flagged below).
- **App factory** (`main.py`): CORS, error handlers, health router; domain routers added per phase.
- **Alembic**: configured to read `DATABASE_URL` from settings and target `Base.metadata`; **no version files yet** (baseline created in V1 once models exist).
- **Frontend**: App Router skeleton; landing page pings backend health; `lib/api` + `lib/config` foundations.

## 4. Security review
- ✅ **No secrets committed.** Only `*.example` files exist; no real `.env`/`.env.local` present.
- ✅ **`.gitignore` verified:** `.env`, `backend/.env`, `frontend/.env.local` are ignored; `.env.example`, `backend/.env.example`, `frontend/.env.local.example` are **tracked** (confirmed via `git check-ignore`).
- ✅ **Local vs prod separation:** host-run defaults in `*.env.example`; compose **overrides** DB/Redis to service names (`db:5432`/`redis:6379`) so the same image runs in either context. Production secrets are intended to live on the VPS (`/etc/wms/*.env`), never in git.
- ✅ **No plaintext credentials in code/compose** beyond local dev placeholders (`wms/wms`); `SECRET_KEY` is a placeholder to be overridden in prod.
- ✅ **CORS** restricted to the frontend origin (`CORS_ORIGINS`), not `*`.
- ✅ **Datastore isolation from SPIR:** distinct compose project (`wms`), network (`wms_net`), volumes (`wms_pgdata`/`wms_redisdata`), and host ports.
- ℹ️ **Auth not present yet** (V1): no JWT/password handling in V0 by design.

## 5. Environment variables

**Root `.env` (compose)** — `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `FRONTEND_PORT=3100`, `BACKEND_PORT=8100`, `POSTGRES_PORT=5433`, `REDIS_PORT=6381`.

**`backend/.env`** — `ENV`, `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `BACKEND_PORT`, `CORS_ORIGINS`, `PRODUCT_NAME`. (Compose overrides `DATABASE_URL`/`REDIS_URL`/`CELERY_BROKER_URL`/`CORS_ORIGINS` for in-container networking.)

**`frontend/.env.local`** — `NEXT_PUBLIC_API_BASE_URL=http://localhost:8100/api/v1`, `NEXT_PUBLIC_PRODUCT_NAME=CoreOps`.

## 6. Docker architecture

Compose project **`wms`** (isolated from SPIR). Host → container port map:

| Service | Image | Host | Container | Notes |
|---|---|---|---|---|
| `db` | postgres:16 | **5433** | 5432 | vol `wms_pgdata`; healthcheck `pg_isready` |
| `redis` | redis:7 | **6381** | 6379 | vol `wms_redisdata`; healthcheck `redis-cli ping` |
| `backend` | ./backend | **8100** | 8000 | uvicorn `--reload`; waits for db/redis healthy |
| `worker` | ./backend | — | — | celery worker (no tasks in V0) |
| `frontend` | ./frontend | **3100** | 3100 | `next dev -p 3100` |

Network `wms_net` (bridge). SPIR's 3000/8000/5432/6379 untouched.

## 7. Local startup instructions

**Option A — Docker (recommended):**
```bash
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local
docker compose up --build
# Frontend  http://localhost:3100
# Backend   http://localhost:8100/api/v1/health   → {"status":"ok"}
# API docs  http://localhost:8100/api/v1/docs
# Readiness http://localhost:8100/api/v1/health/ready
```

**Option B — Host backend + Dockerized datastores:**
```bash
cp .env.example .env && docker compose up -d db redis
cd backend && cp .env.example .env
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8100
pytest                      # runs the health smoke test
# new shell:
cd frontend && cp .env.local.example .env.local && npm install && npm run dev
```

## 8. Verification performed (and not)
**Verified in this environment:** all backend Python passes `py_compile`; `docker-compose.yml` parses (project `wms`, 5 services); `package.json`/`tsconfig.json` valid JSON; `.gitignore` correctly ignores real env files and tracks `*.example`.
**Not run here** (no deps/Docker provisioned): `pytest`, `uvicorn`, `npm install`, `docker compose up`. Run them via §7 to confirm at runtime.

## 9. Deviations / notes (for sign-off)
1. **`GET /health/ready`** added beyond the OpenAPI `/health` — an operational DB+Redis probe. `/health` itself matches the contract exactly. *(Remove if you want strict contract-only.)*
2. **Frontend listens on 3100 inside the container** (mapped `3100:3100`) for symmetry with the `next dev -p 3100` script, instead of container `3000`. Host port is **3100** as specified. Backend keeps container `8000` → host `8100`.
3. **`worker` (Celery) service** is present per the approved stack but defines **no tasks** in V0.
4. **No Alembic version files** yet — baseline migration is created in V1 with the first models.
5. **Not committed to git** — files are in the working tree; awaiting your go-ahead to commit (and to start V1).

---

**Awaiting approval to begin V1 — Authentication** (User, Role, JWT, password hashing, login, logout, current user).
