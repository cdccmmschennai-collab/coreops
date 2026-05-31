# V1 — Authentication: Implementation Plan

**Date:** 2026-05-31 · **Phase:** V1 (build order Step 1) · **Status:** plan only — **no code until approved.**

Implements the first slice of the system: **identity + access**. Strictly follows `V1_ARCHITECTURE_PACKAGE.md` and `api/openapi-v1.yaml`. Carries the V0 audit remediations (F1–F7) as the opening work.

---

## 1. Scope

**In:** `users` table + `user_role` enum · password hashing · JWT issue/verify · `POST /auth/login` · `POST /auth/logout` (token revocation) · `GET /auth/me` · `get_current_user` + `require_role` dependencies · admin user bootstrap · the admin-only **users** management endpoints that depend only on identity (`GET/POST /users`, `PATCH /users/{id}`, `/role`, `/password`).

**Out (later phases):** employees, projects, attendance, reports, dashboard; SSO/MFA; password-reset-by-email; refresh tokens (see Decision D-V1-3); rate limiting beyond a basic login guard (Decision D-V1-5).

**Endpoints delivered (exact, per OpenAPI):**
`/auth/login`, `/auth/logout`, `/auth/me`, `/users`, `/users/{id}`, `/users/{id}/role`, `/users/{id}/password`.

---

## 2. Pre-work — apply V0 audit remediations (first commit of V1)

| Ref | Action |
|---|---|
| F1 | `shared/errors.py`: use `jsonable_encoder(exc.errors())`; pass `status_code` explicitly (remove `request.state` mutation). |
| F2 | Add generic `Exception` handler → `{"error":{"code":"internal_error",...}}`, no internals leaked. |
| F3 | `alembic.ini`: `path_separator` → **`version_path_separator = os`**. |
| F4 | Add `backend/entrypoint.sh` → `alembic upgrade head` then exec CMD; wire into compose for `backend` (not `worker`). |
| F6 | `config.py`: validator — when `ENV != "local"`, reject default/short `SECRET_KEY` (fail fast on boot). |
| F7 | **Drop `passlib`; use the `bcrypt` package directly** (already transitive). Wrapper in `core/security.py`. (Alt: `argon2-cffi` — see Decision D-V1-1.) |

These are remediations of existing code, not new features.

---

## 3. Data model & migration

**Enum + table** exactly per `V1_ARCHITECTURE_PACKAGE.md` §3 (`users`, `user_role`).

- ORM model: `app/modules/users/models.py` → `User(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin)` with `email (citext, unique-where-alive)`, `password_hash`, `role`, `is_active`, `last_login_at`.
- **Alembic baseline `0001_users`** (incremental, per-module — not one giant baseline):
  1. `CREATE EXTENSION IF NOT EXISTS pgcrypto;` and `citext;` (F5)
  2. `CREATE TYPE user_role AS ENUM ('admin','manager','employee','viewer');`
  3. `users` table + partial-unique index on `email WHERE deleted_at IS NULL`.
- `alembic/env.py`: add `import app.modules.users.models  # noqa: F401` so autogenerate sees it.
- **Decision:** migrations are **incremental per module** (0001=users, later 0002=employees, …) rather than a single baseline. Cleaner for phased delivery; noted as a deliberate deviation from the package's "baseline creates all 5 tables."

---

## 4. Security module (`app/core/security.py`)

**Password hashing** — `bcrypt` directly (D-V1-1):
- `hash_password(raw) -> str` (bcrypt, cost 12); `verify_password(raw, hash) -> bool`. Constant-time compare via bcrypt.
- Reject passwords > 72 bytes pre-hash (bcrypt limit) with a clear 422.

**JWT** — HS256 with `SECRET_KEY` (D-V1-2):
- Access token claims: `sub` (user id), `role`, `iat`, `exp` (`ACCESS_TOKEN_EXPIRE_MINUTES`), `jti` (uuid, for revocation).
- `create_access_token(user) -> str`; `decode_token(token) -> claims` (raises on expiry/signature).

**Revocation (logout)** — Redis denylist (D-V1-4):
- On logout: `SET denylist:<jti> 1 EX <seconds-until-exp>` so the key self-expires with the token.
- On every authenticated request: reject if `denylist:<jti>` exists.

---

## 5. Modules

### 5.1 `app/modules/auth/`
- `schemas.py`: `LoginRequest{email,password}`, `TokenResponse{access_token,token_type,expires_in}`, `Me{user, employee?}` (employee always `null` in V1 — table arrives next phase).
- `service.py`: `authenticate(email, password)` → verify active user + hash; on success set `last_login_at`, issue token; on failure raise `AppError("invalid_credentials", 401)`. Basic **login throttle** (D-V1-5): Redis counter per email+IP, soft lock after N failures.
- `router.py`: `POST /auth/login`, `POST /auth/logout` (revoke current `jti`), `GET /auth/me`.

### 5.2 `app/modules/users/` (admin identity management)
- `schemas.py`: `User`, `UserCreate{email,password,role}`, `UserUpdate{is_active?,role?}`, `UserPage`.
- `service.py`: create (hash password, unique-email → 409), list (pagination + `q` ILIKE on email), update, set role, set password.
- `router.py`: `GET/POST /users`, `GET/PATCH /users/{id}`, `PATCH /users/{id}/role`, `PATCH /users/{id}/password` — all `require_role("admin")`.

### 5.3 Dependencies (`app/core/deps.py`)
- `get_current_user(token) -> User`: decode JWT → check denylist → load user → ensure `is_active` and not soft-deleted → else 401.
- `require_role(*roles)`: dependency factory → 403 if `current_user.role` not in `roles`. (Coarse RBAC per `USER_ROLES_AND_PERMISSIONS.md` v1; scoped checks land with employees.)
- Register `auth` + `users` routers in `main.py` under `/api/v1`.

---

## 6. Admin bootstrap

- `backend/scripts/seed_admin.py` (or `database/seeds/`): idempotent — reads `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` from env; creates an `admin` user if none exists; safe to re-run.
- Add `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` to `backend/.env.example` (placeholders).
- Run manually post-migrate: `python -m scripts.seed_admin` (documented; **not** in migrations, not auto-run in prod).

---

## 7. Role enforcement (this phase)

| Endpoint | admin | manager | employee | viewer |
|---|:--:|:--:|:--:|:--:|
| `/auth/*` | ✓ | ✓ | ✓ | ✓ |
| `GET/POST /users`, `PATCH /users/{id}`, `/role`, `/password` | ✓ | — | — | — |

Deny-by-default; all `/users` mutations admin-only; an admin cannot remove their own admin role or deactivate themselves if they are the last active admin (guard → 409).

---

## 8. Error mapping (uniform envelope)
`invalid_credentials`→401 · `unauthorized` (missing/expired/revoked token)→401 · `forbidden`→403 · `not_found`→404 · `conflict` (dup email / last-admin)→409 · `validation_error`→422.

---

## 9. Testing plan (TDD-first)

- **Unit:** hashing round-trip + wrong password; JWT encode/decode + expiry + tamper; denylist add/check.
- **Integration (TestClient + ephemeral test DB, transactional rollback):**
  - login success → token; login wrong password → 401; inactive user → 401.
  - `me` with valid/expired/revoked token.
  - logout → token rejected afterward.
  - `require_role`: employee hitting `/users` → 403; admin → 200.
  - create user dup email → 409; set password → login with new password.
  - last-admin guard → 409.
- **Migration test:** `alembic upgrade head` then `downgrade base` on a scratch DB in CI.
- Extend `conftest.py` with a `db`/`session` fixture and an `auth_client(role)` helper.

---

## 10. Build order (within V1)
1. Remediations F1–F4, F6, F7 (+ test the new error envelope).
2. `core/security.py` (+ unit tests).
3. `users` model + Alembic `0001_users` (+ migration test); wire `env.py`.
4. `get_current_user` / `require_role` in `deps.py`.
5. `auth` module (login/logout/me) (+ tests).
6. `users` admin module (+ tests).
7. `seed_admin` script + env vars + entrypoint wiring (F4).
8. Update `backend/README.md`; run full `pytest`; manual smoke via Docker.

---

## 11. Acceptance criteria
- `docker compose up` → migrations apply → seeded admin can `POST /auth/login` and receive a JWT.
- `GET /auth/me` returns the user; after `POST /auth/logout` the same token is rejected (401).
- Non-admins get 403 on `/users`; admin can create/list/update users and reset passwords.
- All responses (incl. errors) use the uniform envelope; OpenAPI live spec at `/api/v1/docs` reflects the new endpoints and matches `openapi-v1.yaml`.
- `pytest` green; no secrets committed; `SECRET_KEY` guard active for non-local envs.

---

## 12. Decisions for this phase (confirm at approval)
- **D-V1-1 Password hashing:** **bcrypt (cost 12) via the `bcrypt` package directly** (drop passlib). Alt: argon2id. → *recommend bcrypt-direct.*
- **D-V1-2 JWT alg:** **HS256** with `SECRET_KEY` (single-service, symmetric is fine). Revisit RS256 only if tokens must be verified by other services (not in v1).
- **D-V1-3 Refresh tokens:** **none in v1** — single access token, TTL `ACCESS_TOKEN_EXPIRE_MINUTES` (60). Re-login on expiry. (Refresh is a later enhancement.)
- **D-V1-4 Logout:** **stateful revocation via Redis denylist keyed on `jti`**, TTL = token remaining life.
- **D-V1-5 Login throttle:** **basic** Redis counter (per email+IP), soft-lock after N failures for M minutes. Full lockout columns (`failed_login_count`/`locked_until`) are deferred (not in the v1 `users` table).
- **D-V1-6 Migrations:** **incremental per module** (0001=users …), not a single baseline.

> Note: the v1 `users` table (per `V1_ARCHITECTURE_PACKAGE.md` §3) intentionally has **no** `failed_login_count`/`locked_until`/`mfa_*` columns — throttling is Redis-side, MFA is out of scope. If persistent lockout is wanted in v1, that's a small schema add to confirm now.

_Related: [`V0_AUDIT_REPORT.md`](./V0_AUDIT_REPORT.md) · [`V1_ARCHITECTURE_PACKAGE.md`](./V1_ARCHITECTURE_PACKAGE.md) · [`api/openapi-v1.yaml`](./api/openapi-v1.yaml) · [`USER_ROLES_AND_PERMISSIONS.md`](./USER_ROLES_AND_PERMISSIONS.md)._
