# V0 Foundations — Architecture & Implementation Audit

**Date:** 2026-05-31 · **Auditor:** Principal Architect pass · **Subject:** everything generated in V0 (`docker-compose.yml`, `backend/`, `frontend/`) against `V1_ARCHITECTURE_PACKAGE.md`, `V1_IMPLEMENTATION_PLAN.md`, and `api/openapi-v1.yaml`.

## Verdict

**APPROVED to proceed to V1 — conditional on applying the 2 High-severity fixes (F1, F2) as the first commit of V1.** No blockers. The skeleton is sound, isolated from SPIR, and forward-compatible. Findings below are mostly small correctness/robustness items; none require re-architecting.

Severity key: 🔴 Blocker · 🟠 High (fix before/at V1 start) · 🟡 Medium (fix during V1) · 🔵 Low · ⚪ Info.

---

## 1. Validation results (10 areas)

| # | Area | Result | Notes |
|---|---|---|---|
| 1 | FastAPI architecture | ✅ Pass | App factory, CORS, error envelope, health router, thin-router convention. Two robustness bugs in the error handler (F1). |
| 2 | Next.js architecture | ✅ Pass | App Router, `@/*` alias, single brand token, health-ping landing. Minor: no `metadata` server/client split needed yet. |
| 3 | Docker architecture | ✅ Pass | `wms` project, isolated net/volumes, healthchecks on db/redis, correct host ports. Backend has no migration entrypoint yet (needed in V1, F4). |
| 4 | PostgreSQL setup | ✅ Pass | SQLAlchemy 2.0 engine, `pool_pre_ping`, `get_db`, `Base`. `pgcrypto`/`citext` extensions not yet created (created by the V1 baseline migration — F5). |
| 5 | Redis setup | ✅ Pass | Shared client, `decode_responses=True`, used by readiness. Denylist usage arrives in V1. |
| 6 | Alembic configuration | 🟡 Needs fix | Wired to settings + `Base.metadata`, `compare_type=True`. **`alembic.ini` uses an invalid key** (F3). No version files yet (correct for V0). |
| 7 | Env var handling | ✅ Pass | pydantic-settings; nothing hardcoded; compose overrides for in-container networking; reads `os.environ` so Docker works without a `.env` file in the image. |
| 8 | Security practices | ✅ Pass (with V1 items) | No secrets committed; `.gitignore` verified; CORS scoped. `SECRET_KEY` default must be guarded before auth (F6); login throttling is a V1 concern. |
| 9 | Future extensibility | ✅ Pass | `modules/` package, base mixins, error envelope, pagination, `manager_id`, attendance `source` enum hook for biometrics — all in place. Details below. |
| 10 | SPIR compatibility | ✅ Pass | Distinct project/network/volumes/ports (3100/8100/5433/**6381**). One pre-deploy check recommended (F8). |

---

## 2. Findings

### 🟠 High

**F1 — Error handler: non-serializable validation payload + `request.state` mutation hack** (`backend/app/shared/errors.py`)
`RequestValidationError.errors()` can contain non-JSON-serializable objects (e.g. exception instances under `ctx`); passing it straight into `JSONResponse(content=...)` can raise a 500 *during* error handling. Also, status code is stashed on `request.state._status_code` and read back — fragile and unidiomatic.
**Fix:** wrap with `fastapi.encoders.jsonable_encoder(exc.errors())`; pass `status_code` explicitly into the envelope builder instead of via `request.state`. Add a generic `Exception` handler returning a 500 envelope (no stack-trace leak).

**F2 — No generic 500 handler / unhandled-exception envelope**
Unexpected exceptions currently fall through to FastAPI's default (non-enveloped) 500. For a system that promises a uniform error contract, add a catch-all returning `{"error":{"code":"internal_error",...}}` without leaking internals.

### 🟡 Medium

**F3 — `alembic.ini` invalid key** — line 6 sets `path_separator = os`; Alembic 1.13.x expects **`version_path_separator = os`**. The current key is ignored (harmless with one versions dir, but incorrect). **Fix:** rename to `version_path_separator = os`.

**F4 — No DB migration entrypoint for the backend container** — compose runs `uvicorn` directly. From V1 (when migrations exist) the container must run `alembic upgrade head` before serving. **Fix:** add `backend/entrypoint.sh` (idempotent: `alembic upgrade head` then exec the CMD) and use it in compose, OR a compose `command` that chains them.

**F5 — Extensions not yet provisioned** — schema needs `pgcrypto` (`gen_random_uuid()`) and `citext`. **Fix:** the V1 baseline migration (`0001`) must `CREATE EXTENSION IF NOT EXISTS pgcrypto; citext;` before creating tables. (Not a V0 defect — noted so it isn't missed.)

**F6 — `SECRET_KEY` default is an insecure placeholder** — fine for V0 (no auth), but the moment JWT lands this must never run with the default outside `local`. **Fix (V1):** validate in `config.py` that `ENV != "local"` ⇒ `SECRET_KEY` differs from the placeholder and meets a min length; fail fast on boot.

**F7 — Dependency risk: passlib + bcrypt** — `requirements.txt` pins `passlib[bcrypt]==1.7.4` with an unpinned modern `bcrypt`. passlib 1.7.4 logs an error / can misbehave with `bcrypt>=4.1` (`AttributeError: module 'bcrypt' has no attribute '__about__'`). **Fix (V1):** either use the **`bcrypt` package directly** (drop passlib) or pin `bcrypt<4.1`. Recommendation in `V1_AUTHENTICATION_PLAN.md` → use `bcrypt` directly (one less unmaintained dep) or `argon2-cffi`.

### 🔵 Low

**F8 — Pre-deploy port check (SPIR)** — co-existence relies on host ports 3100/8100/5433/6381 being free on the VPS. Not a code issue; add a deploy-time check (`ss -ltnp`) in the (later) deployment runbook.
**F9 — No backend/frontend healthchecks in compose** — only `db`/`redis` have them; adding HTTP healthchecks for `backend` (`/api/v1/health`) and `frontend` improves `depends_on` correctness. Optional.
**F10 — `worker` service has no tasks** — intended (declared per stack). Consider `profiles: [workers]` so it isn't started by default until needed, to save local resources.
**F11 — `CORS allow_credentials=True`** — v1 uses bearer-token auth (Authorization header), not cookies, so credentials aren't required; can be `False`. Harmless but tighten when convenient.
**F12 — No CI config** — `V1_IMPLEMENTATION_PLAN.md` §13 mentioned "CI lint" in V0; not created. Low priority; add `ruff`+`pytest` CI when convenient.

### ⚪ Info / confirmations
- **No missing critical files** for V0 scope. `database/` (schema-v1.sql) and `docker-compose.prod.yml` are intentionally absent (created in V1 / deployment phase).
- **Naming:** consistent — `PRODUCT_NAME`/`NEXT_PUBLIC_PRODUCT_NAME = CoreOps` (single brand token), db/role `wms`, compose project `wms`. The full-design `worktrack`/`worktrack_audit` schema names are **not** used in v1 (v1 uses the `public` schema in db `wms`) — consistent and intentional.
- **Deviations already logged** in `V0_FOUNDATIONS_REPORT.md` (extra `/health/ready`; frontend 3100-in-container; worker no-tasks) remain acceptable.
- **Health liveness** matches the OpenAPI contract exactly (`{"status":"ok"}`).

---

## 3. Extensibility review (area 9, detail)

| Future module | Ready? | Hook present | Gap to close in its phase |
|---|---|---|---|
| **Employees** | ✅ | `modules/` pkg, base mixins, `get_db`, error envelope | Add `employees` model + migration + router; `manager_id` self-FK for scoping |
| **Projects** | ✅ | same foundations | Add `projects` model + migration + router |
| **Daily Reports** | ✅ | same | `daily_reports` model; unique (employee, date); review workflow |
| **Attendance** | ✅ | `attendance_status`/`source` enums planned | `attendance_logs` model; check-in/out logic |
| **Biometric integration** (future, not v1) | ✅ path exists | `attendance_logs.source` enum is designed to gain `biometric`; raw events ingested via a future ACL | Postgres enum value add via migration; device-auth ingestion endpoint; **never store raw biometrics** (per `INTEGRATIONS.md`) |

No structural barrier to any of the above. The modular-monolith layout and per-module `router/schemas/models/service` convention scale cleanly to V1.x phases.

---

## 4. Required actions before/at V1 start

1. **F1 + F2** (🟠) — harden the error handler (jsonable_encoder, explicit status, generic 500). *Apply as the first commit of V1.*
2. **F3** (🟡) — fix `alembic.ini` key.
3. **F7** (🟡) — resolve the password-hashing dependency (decided in `V1_AUTHENTICATION_PLAN.md`).
4. **F4, F5, F6** (🟡) — fold into the V1 Authentication build (entrypoint, baseline-migration extensions, secret-key guard).

Low items (F8–F12) are backlog, not gating.

---

## 5. Scope discipline
No new features were written during this audit. Two of the above (F1/F2) are **remediations of existing V0 code**, not new functionality; they will be applied at the start of V1 alongside the Authentication work, per the plan in `V1_AUTHENTICATION_PLAN.md`.

_Related: [`V0_FOUNDATIONS_REPORT.md`](./V0_FOUNDATIONS_REPORT.md) · [`V1_AUTHENTICATION_PLAN.md`](./V1_AUTHENTICATION_PLAN.md) · [`V1_ARCHITECTURE_PACKAGE.md`](./V1_ARCHITECTURE_PACKAGE.md) · [`api/openapi-v1.yaml`](./api/openapi-v1.yaml)._
