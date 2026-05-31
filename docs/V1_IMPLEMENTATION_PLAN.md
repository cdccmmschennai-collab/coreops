# Workforce Management System — v1 Implementation Plan

> **Phase:** Implementation planning & architecture validation. **No code.** Brand-agnostic (codename **CoreOps**; the product name remains a single config token — D-001).
>
> **Mandate:** ship a **stable v1** on the **existing stack** (FastAPI · PostgreSQL · Redis · Celery · Next.js), **co-hosted** with the existing **SPIR Dynamic Extraction** system on the shared VPS, **without interfering** with it. Deliberately small: the rich design in `DOMAIN_MODEL.md` / `databasedesign.md` is the *north star*, but v1 implements a **minimal, forward-compatible subset**.

---

## 0. Hard constraints (honored throughout)

| Rule | How v1 complies |
|---|---|
| No microservices | Single FastAPI **modular monolith** + single Next.js app |
| No Kubernetes | Plain Linux processes (systemd) or a single docker-compose project |
| No event bus initially | Direct in-process calls; events deferred (`EVENT_ARCHITECTURE.md` is post-v1) |
| No AI initially | `AI_ROADMAP.md` deferred entirely |
| No recruitment initially | Recruitment context excluded |
| No biometric initially | Attendance is web/manual only (`source` kept for future) |
| No multi-tenant initially | Single-tenant; **no `tenant_id`** in v1 schema (RLS path documented for later) |
| No framework rewrites | Reuse SPIR's stack exactly |
| No overengineering | 5 tables, simple role column, synchronous flows, Celery only if needed |

---

## 1. Architecture validation (review of existing docs vs v1)

Reviewed: `architecture.md`, `backenddesign.md`, `frontenddesign.md`, `databasedesign.md`, `DOMAIN_MODEL.md`, `WORKFLOWS.md`, `USER_ROLES_AND_PERMISSIONS.md`, `TENANCY_STRATEGY.md`, `EVENT_ARCHITECTURE.md`, `INTEGRATIONS.md`, `AI_ROADMAP.md`, `roadmap.md`, `IMPLEMENTATION_SEQUENCE.md`, `decisions.md`.

**Bounded contexts required for v1** (from `DOMAIN_MODEL.md`):

| Context | v1? | v1 scope |
|---|---|---|
| Identity & Access | ✅ partial | login, sessions (JWT), simple role on user; **no scoped RBAC, no SSO/MFA** |
| Employee Management | ✅ partial | employee directory + manager link; **no employment_history** |
| Org Structure | ⚠️ folded | department/designation as **plain columns** on employee; no departments/locations/shifts tables |
| Project Management | ✅ partial | projects + simple membership; **no stints/activity_types** |
| Work Reporting | ✅ partial | one daily report per employee/day with a primary project; **no entries table, no @mentions, no versioning** |
| Attendance | ✅ partial | check-in/out logged to `attendance_logs`; **no punch stream/aggregator, no corrections, no leave/holidays** |
| Leave | ❌ deferred | — |
| Notifications | ❌ deferred | (in-app badge optional later) |
| Audit & Compliance | ⚠️ minimal | `created_by`/`updated_by` + timestamps only; **no audit_logs table in v1** |
| Analytics | ⚠️ minimal | dashboard reads simple aggregates; no replica/heatmaps |
| Recruitment / Biometric / AI | ❌ deferred | — |

**Validation result:** v1 scope is consistent with the documented architecture as a **strict subset**. No constraint is violated. Forward-compatibility is preserved by keeping the conventions that make the later migration cheap (UUID PKs, `created_at/updated_at`, soft-delete `deleted_at`, `manager_id` for future org scoping, `source` on attendance for future biometrics). **Open decisions that v1 intentionally sidesteps:** U-010 (tenancy — single-tenant now), U-002 (report lock rule — pick the simpler "editable until end of day" for v1), U-007 (count semantics — v1 uses generic fields, see §6).

---

## 2. Minimal implementation roadmap (v1)

Maps to `IMPLEMENTATION_SEQUENCE.md` S0–S5, compressed.

| Stage | Theme | Outcome |
|---|---|---|
| **V0 — Foundations** | repo, env, ports, local DB/Redis, FastAPI+Next skeletons, Alembic, CI lint | App boots on 8100/3100; migrations run on 5433 |
| **V1.1 — Auth & Users** | JWT login, password hashing, `users`, role, `/me` | Sign in → token → role-gated routes |
| **V1.2 — Employees** | employee CRUD, manager link, directory UI | Admin manages people; employees see profile |
| **V1.3 — Projects** | project CRUD + membership, projects UI | Projects exist and are assignable |
| **V1.4 — Attendance** | check-in/out, `attendance_logs`, calendar/history UI | Daily presence captured |
| **V1.5 — Daily Reports** | report submit/list, link to project, reports UI | Core reporting loop works |
| **V1.6 — Dashboard** | KPIs from existing tables | Home shows today/this-week summary |
| **V1.7 — Hardening & Deploy** | tests, .env split, nginx subdomain, systemd, backups | Live alongside SPIR, isolated |

---

## 3. Backend folder structure (FastAPI modular monolith)

```
backend/
├── app/
│   ├── main.py                     # FastAPI app factory, router registration, CORS
│   ├── core/
│   │   ├── config.py               # pydantic-settings; reads .env (ports, DB, redis, secret)
│   │   ├── security.py             # password hashing, JWT encode/decode
│   │   ├── database.py             # SQLAlchemy engine/session (Postgres :5433)
│   │   ├── deps.py                 # get_db, get_current_user, require_role
│   │   └── celery_app.py           # Celery app (broker redis :6381) — minimal, optional in v1
│   ├── modules/
│   │   ├── auth/                   # router.py, schemas.py, service.py
│   │   ├── users/                  # router, models.py, schemas, service
│   │   ├── employees/              # router, models, schemas, service
│   │   ├── attendance/             # router, models, schemas, service
│   │   ├── projects/               # router, models, schemas, service
│   │   └── daily_reports/          # router, models, schemas, service
│   └── shared/
│       ├── base_model.py           # id(uuid), created_at, updated_at, deleted_at mixin
│       ├── pagination.py
│       └── errors.py               # uniform error envelope
├── alembic/                        # migrations (separate history from SPIR)
│   ├── env.py
│   └── versions/
├── tests/
│   ├── conftest.py                 # test DB, client fixtures
│   ├── test_auth.py … test_daily_reports.py
├── alembic.ini
├── pyproject.toml                  # or requirements.txt (match SPIR's tooling)
├── .env.example                    # committed; real .env is git-ignored
└── README.md
```

**Per-module shape (consistent):** `router.py` (HTTP), `schemas.py` (pydantic in/out), `models.py` (SQLAlchemy), `service.py` (business logic; routers stay thin). Modules import **downward only** (see §11 dependency order); no circular imports.

---

## 4. Frontend folder structure (Next.js, App Router)

```
frontend/
├── src/
│   ├── app/
│   │   ├── (auth)/login/page.tsx
│   │   ├── (app)/
│   │   │   ├── layout.tsx           # AppShell (sidebar + topnav), auth guard
│   │   │   ├── dashboard/page.tsx
│   │   │   ├── employees/page.tsx
│   │   │   ├── attendance/page.tsx
│   │   │   ├── projects/page.tsx
│   │   │   └── reports/page.tsx
│   │   └── layout.tsx               # root, providers
│   ├── components/                  # design-system primitives (Button, Card, Table, Badge…)
│   ├── lib/
│   │   ├── api.ts                   # fetch client → backend :8100, attaches JWT
│   │   ├── auth.ts                  # token storage, session context
│   │   └── hooks/                   # data-fetching hooks
│   ├── styles/                      # tokens (recover colors_and_type — U-005)
│   └── types/                       # shared TS types mirroring API schemas
├── public/                          # logo-mark.svg, favicon
├── next.config.js                   # dev port 3100, API rewrite/proxy
├── .env.local.example               # committed; .env.local git-ignored
├── package.json
└── README.md
```

Design system: port the prototype primitives from `design-assets/ui_kits/web_app/` into `components/`, bind the brand to a single `--product-name`/`Brand` component (D-001). Keep the calm voice (D-013).

---

## 5. Database schema plan (v1 — 5 tables)

Engine: **PostgreSQL on host port 5433** (own database, separate from SPIR). Conventions kept for forward-compatibility: **UUID PK**, `created_at`/`updated_at`, soft-delete `deleted_at`, `numeric` for hours, `timestamptz` everywhere.

```mermaid
erDiagram
  users ||--o| employees : "identity for"
  employees ||--o{ employees : "manages (manager_id)"
  employees ||--o{ attendance_logs : "logs"
  employees ||--o{ daily_reports : "writes"
  projects  ||--o{ daily_reports : "logged against"
  employees ||--o{ projects : "owns (optional)"
```

| Table | Key columns (v1) | Notes / future path |
|---|---|---|
| **users** | id, email (unique, citext), password_hash (nullable for future SSO), **role** enum(`admin`,`manager`,`employee`,`viewer`), is_active, last_login_at, created_at, updated_at, deleted_at | Simplified `auth_users`. Sessions via JWT (no sessions table in v1; optional Redis denylist for logout). |
| **employees** | id, user_id (FK→users, nullable), employee_code (unique), first_name, last_name, work_email, phone, **department** (text), **designation** (text), **manager_id** (self-FK, RESTRICT), date_of_joining, status enum(`active`,`on_leave`,`exited`), created_at, updated_at, deleted_at | Org structure folded into columns. `manager_id` enables manager scoping now and full hierarchy later. |
| **attendance_logs** | id, employee_id (FK), log_date (date), check_in_at, check_out_at, status enum(`present`,`wfh`,`leave`,`holiday`,`weekend`,`absent`), **source** enum(`web`,`manual`,`system`), total_minutes (int), note, created_by, created_at, updated_at | **unique(employee_id, log_date)**. Simplified merge of punches+records; biometric `source` reserved. No aggregator worker in v1 (write on check-out). |
| **projects** | id, code (unique), name, description, status enum(`active`,`on_hold`,`completed`,`archived`), owner_employee_id (FK, SET NULL), start_date, end_date, allocated_hours (numeric), color, created_at, updated_at, deleted_at | Membership for v1 = `daily_reports.project_id` + optional `owner`. No `project_members`/`activity_types` table yet. |
| **daily_reports** | id, employee_id (FK, RESTRICT), report_date (date), project_id (FK, nullable, RESTRICT), hours (numeric), tasks_done (int), tasks_open (int), remarks (text), status enum(`draft`,`submitted`,`approved`,`rejected`), reviewed_by (FK, SET NULL), reviewed_at, created_at, updated_at, deleted_at | **unique(employee_id, report_date)**. Flattened single-entry report (one primary project). Counts kept generic (`tasks_done/open`) — domain-specific counts (BOM/Spares/Tags) deferred pending U-007. Entries-table normalization is the documented upgrade path. |

**Indexes (v1):** unique `users(email) where deleted_at is null`; `employees(manager_id)`, `employees(employee_code) unique`; `attendance_logs(employee_id, log_date) unique`; `daily_reports(employee_id, report_date) unique`, `daily_reports(status, report_date)`. **No partitioning, no RLS, no `tenant_id`** in v1.

---

## 6. API module plan

Base: `/api/v1`. JWT bearer. Uniform error envelope. Pagination on lists.

| Module | Endpoints (v1) |
|---|---|
| **auth** | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` |
| **users** | `GET /users`, `POST /users`, `GET /users/{id}`, `PATCH /users/{id}` (admin), `PATCH /users/{id}/role` (admin) |
| **employees** | `GET /employees` (filter/search), `POST /employees`, `GET /employees/{id}`, `PATCH /employees/{id}`, `GET /employees/{id}/team` (manager) |
| **attendance** | `POST /attendance/check-in`, `POST /attendance/check-out`, `GET /attendance?employee&month`, `GET /attendance/me` |
| **projects** | `GET /projects`, `POST /projects`, `GET /projects/{id}`, `PATCH /projects/{id}` |
| **daily_reports** | `GET /reports` (self/team/all by role), `POST /reports`, `GET /reports/{id}`, `PATCH /reports/{id}`, `POST /reports/{id}/submit`, `POST /reports/{id}/review` |
| **dashboard** | `GET /dashboard/summary` (KPIs from existing tables) |
| **health** | `GET /health` (liveness/readiness for nginx + monitoring) |

Routers thin; logic in `service.py`. CORS limited to the frontend origin. OpenAPI auto-served by FastAPI (`/api/v1/docs`) — the contract gap (G2) closes for free.

---

## 7. Permission model plan (v1 — simple, not scoped RBAC)

v1 uses a **single `role` column** on `users` + **manager relationship** for team scoping. The full scoped RBAC (`USER_ROLES_AND_PERMISSIONS.md`, D-014) is the documented upgrade path; v1 deliberately does **not** build `roles/permissions/user_roles`.

| Role | v1 capability |
|---|---|
| **admin** | everything: manage users/employees/projects, see all reports/attendance, review |
| **manager** | view & review reports for **own team** (employees where `manager_id = self`); view team attendance; read projects |
| **employee** | own attendance (check-in/out), own reports (submit/edit until end of day), own profile |
| **viewer** | read-only dashboards/projects |

**Enforcement:** FastAPI dependency `require_role(...)` for coarse gating + **row-level filters in services** (e.g. manager queries bounded by `manager_id`; employee queries bounded to `self`). Deny-by-default. Author ≠ approver (separation of duties) for report review.

**Upgrade path (documented, not built):** replace the enum with `roles`+`user_roles(scope_type, scope_id)` and swap `require_role` for permission-key checks — no API shape change required.

---

## 8. Migration strategy

- **Tool:** **Alembic** (SQLAlchemy), its own history in `backend/alembic/` — **completely separate** from any SPIR migrations and pointing at the **v1 database on :5433**.
- **Flow:** model change → `alembic revision --autogenerate` → **review the generated SQL** → `alembic upgrade head`. Forward-only; reversible where safe.
- **Baseline:** first migration creates the 5 tables + enums + indexes.
- **Safety:** never autogenerate against SPIR's DB; distinct DB name + role; large-table patterns (CONCURRENTLY) unnecessary at v1 scale but adopted later.
- **Env-driven URL:** Alembic reads `DATABASE_URL` from env (no hardcoded creds).
- **Seed:** a separate, idempotent seed script for the first admin user + a couple of demo roles (run manually, not in migrations).

---

## 9. Git strategy

- **Repo:** single repo (`coreops`) containing `backend/` + `frontend/` (+ `docs/`). `design-assets/` stays read-only.
- **Branching (trunk-based, light):** `main` is protected and always deployable; short-lived `feature/<module>` branches (e.g. `feature/auth`, `feature/attendance`); PR + review; **squash merge**.
- **Commits:** Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`). 
- **Releases:** tag `v1.0.0` at v1 completion; CHANGELOG optional.
- **Quality gates (recommended, not overengineered):** pre-commit hooks — `ruff`/`black` (backend), `eslint`/`prettier` (frontend); CI runs lint + tests on PR.
- **Protected `main`:** require PR + green CI before merge.

---

## 10. Security & configuration (env handling)

**Rules:** never commit `.env` / secrets; commit `*.example` only; separate local vs production config.

**Recommended `.gitignore` additions** (root):
```gitignore
# Python
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.coverage
# Node / Next
node_modules/
.next/
out/
# Env & secrets  (commit ONLY the *.example files)
.env
.env.*
!.env.example
!.env.local.example
*.key
*.pem
secrets/
# OS / editor
.DS_Store
.idea/
.vscode/
```

**`backend/.env.example`** (committed; values are placeholders):
```env
ENV=local
SECRET_KEY=change-me
ACCESS_TOKEN_EXPIRE_MINUTES=60
DATABASE_URL=postgresql+psycopg://wms:CHANGE_ME@localhost:5433/wms
REDIS_URL=redis://localhost:6381/0
CELERY_BROKER_URL=redis://localhost:6381/1
BACKEND_PORT=8100
CORS_ORIGINS=http://localhost:3100
PRODUCT_NAME=CoreOps
```

**`frontend/.env.local.example`** (committed):
```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8100/api/v1
PORT=3100
NEXT_PUBLIC_PRODUCT_NAME=CoreOps
```

**Local vs production separation:** local uses `.env` / `.env.local` (git-ignored); production secrets live **only on the VPS** (in `/etc/wms/backend.env` referenced by systemd, mode 600, not in the repo). No secret ever enters git history.

---

## 11. Infrastructure & co-existence with SPIR (no interference)

**Port map (v1 uses the assigned non-default ports):**

| Service | SPIR (existing) | WMS v1 (new) |
|---|---|---|
| Frontend (Next.js) | 3000 | **3100** |
| Backend (FastAPI) | 8000 | **8100** |
| PostgreSQL | 5432 (assumed) | **5433** (own instance/DB) |
| Redis | 6379 (assumed) | **6381** (own instance; Celery uses DB 1) |

**Isolation guarantees:**
- **Separate datastores:** dedicated Postgres on 5433 and Redis on 6381 — SPIR's 5432/6379 are never touched. (If sharing one Postgres server is later preferred, use a dedicated DB + role; v1 assumes a separate instance per the port spec.)
- **Separate processes:** systemd units `wms-backend.service` (uvicorn :8100), `wms-frontend.service` (next :3100), optional `wms-worker.service` (Celery) — independent of SPIR's units.
- **Separate reverse-proxy block:** a **new nginx server block** for a new subdomain (placeholder `wms.cdccmms.com` — final name TBD, configurable) → `/` to :3100, `/api` to :8100; TLS via the existing certbot. **SPIR's nginx blocks are not modified.**
- **Local dev option:** a **separate docker-compose project** (`-p wms`) bringing up only Postgres:5433 + Redis:6381 with distinct volumes/network so it cannot collide with SPIR containers. App processes run on the host (8100/3100).
- **Celery in v1:** present in the stack but **used minimally or not at all** (synchronous flows preferred). Reserved for later (digest emails, attendance close). No event bus.

---

## 12. Module dependency order

```mermaid
flowchart LR
    core[core: config/db/security/deps] --> auth
    auth --> users
    users --> employees
    employees --> projects
    employees --> attendance
    employees --> daily_reports
    projects --> daily_reports
    attendance --> dashboard
    daily_reports --> dashboard
```

Build order: **core → auth → users → employees → projects → attendance → daily_reports → dashboard**. Each module depends only on those to its left.

---

## 13. Development sequence (step-by-step)

1. **V0 Foundations:** scaffold `backend/` + `frontend/` per §3/§4; add `.gitignore` + `.env.example` (§10); bring up Postgres:5433 + Redis:6381 (docker-compose `-p wms`); FastAPI boots on 8100 with `/health`; Next.js boots on 3100; `core` (config/db/security/deps); Alembic init + empty baseline; CI lint.
2. **V1.1 Auth & Users:** `users` model + baseline migration; password hashing + JWT; `/auth/login`, `/auth/me`, `/auth/logout`; `require_role`; seed first admin; frontend **login** page + auth guard + AppShell.
3. **V1.2 Employees:** `employees` model + migration; CRUD + `manager_id`; team query; frontend **employees** directory + profile.
4. **V1.3 Projects:** `projects` model + migration; CRUD; frontend **projects** list/detail.
5. **V1.4 Attendance:** `attendance_logs` model + migration; check-in/out + month/history queries; frontend **attendance** calendar/history + punch.
6. **V1.5 Daily Reports:** `daily_reports` model + migration; submit/edit/list + review (manager/admin); frontend **reports** form + history.
7. **V1.6 Dashboard:** `/dashboard/summary` aggregates; frontend **dashboard** KPIs.
8. **V1.7 Hardening & Deploy:** finalize tests (§14); split prod env; nginx subdomain + TLS; systemd units; DB backup cron (pg_dump of the v1 DB only); smoke test alongside SPIR; tag `v1.0.0`.

---

## 14. Testing sequence

Build tests **alongside** each module, in this order of reliance:

1. **Unit (services):** business logic per module (auth tokens, role checks, attendance day math, report status transitions) — `pytest`.
2. **API/integration:** FastAPI `TestClient` + a **dedicated test database** (transactional rollback per test); cover each endpoint's happy path + authz (role gating, manager scoping, author≠approver).
3. **Migration tests:** `alembic upgrade head` then `downgrade` on a scratch DB in CI.
4. **Frontend component tests:** key components (forms, tables, AppShell guard).
5. **End-to-end (smoke):** Playwright for the critical path — **login → dashboard → submit report → check-in → manager review** — against the dev stack (3100/8100).
6. **Deploy smoke:** post-deploy health + login check on the staging subdomain, confirming SPIR is unaffected (its endpoints still 200).

**Per-module Definition of Done:** migration (reviewed, reversible) · service unit tests · API tests incl. authz · minimal UI · no secret in repo · docs/OpenAPI current.

---

## 15. Explicitly deferred (post-v1, already designed)
Leave · full Attendance pipeline (punch stream + aggregator + corrections) · Notifications (multi-channel) · Audit log table · Analytics (replica/heatmaps) · Recruitment · Biometric · AI · Multi-tenancy (`tenant_id`+RLS) · scoped RBAC (`roles/permissions/user_roles`) · event bus/outbox · report entries normalization + domain counts (U-007). Each has a documented home in the existing docs and a forward-compatible hook in the v1 schema.

_Related: [`IMPLEMENTATION_SEQUENCE.md`](./IMPLEMENTATION_SEQUENCE.md) · [`PROJECT_STRUCTURE.md`](./PROJECT_STRUCTURE.md) · [`databasedesign.md`](./databasedesign.md) · [`USER_ROLES_AND_PERMISSIONS.md`](./USER_ROLES_AND_PERMISSIONS.md) · [`decisions.md`](./decisions.md)._
