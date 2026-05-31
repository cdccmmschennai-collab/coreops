# V1 Authentication — Completion Report

**Date:** 2026-05-31 · **Branch:** `feature/v1-authentication` · **Status:** complete, tested, smoke-verified. **Next phase (Employees) not started.**

## Scope delivered
Identity + access only: V0 audit remediations, security utilities, `users` table, login/logout/current-user, role enforcement, admin user management, admin bootstrap. No employees/projects/attendance/reports/dashboard.

## Build order — all steps done & committed (small commits)
| Step | Commit | Result |
|---|---|---|
| 1 Audit fixes (F1–F4, F6, F7) | `fix(v0-audit): …` | error envelope hardened; `version_path_separator`; SECRET_KEY guard; bcrypt-direct; migration entrypoint |
| 2 Security utilities | `feat(auth): security utilities …` | bcrypt hash/verify, HS256 JWT create/decode, Redis denylist |
| 3 User model + schemas | `feat(users): User ORM model …` | `users` model + pydantic schemas (regex email, no email-validator dep) |
| 4 Migration 0001_users | `feat(db): alembic migration …` | extensions + `user_role` enum + table; upgrade/downgrade verified reversible |
| 5–8 Login/Logout/Me/Roles | `feat(auth): login/logout/me …` | `/auth/*`, `get_current_user`, `require_role`, Redis login throttle |
| 9 Admin bootstrap | (same commit) | idempotent `scripts/seed_admin.py` |
| 10 Tests | (same commit) | full suite |

## Decisions applied
D-V1-1 bcrypt directly (passlib removed) · D-V1-2 HS256 · D-V1-3 no refresh tokens · D-V1-4 Redis `jti` denylist logout · D-V1-5 Redis login throttle (5 fails / 15 min) · D-V1-6 incremental migrations · **no persistent lockout columns** (Redis-only).

## Tests — 25 passing
- `test_security.py` (7): hash round-trip, >72-byte reject, garbage-hash safe, JWT round-trip, tampered/expired/wrong-signature → `TokenError`.
- `test_health.py` (1): liveness contract.
- `test_auth.py` (9): login success/wrong-pw/inactive/case-insensitive, me with/without token, logout revocation, throttle→429, validation→422.
- `test_users.py` (8): employee 403 vs admin 200, create→login, duplicate 409, set-password→login, set-role, last-admin guard 409, unknown 404.

Run: `docker compose up -d --wait db redis && docker compose run --rm --no-deps --entrypoint pytest backend -q`

## End-to-end smoke (real stack) — verified
`/health` ok → seed creates admin → login (JWT) → `/me` returns admin (`employee: null`) → logout `204` → reuse token `401` (revoked) → re-run seed idempotent.

## Endpoints live (match `openapi-v1.yaml`)
`POST /api/v1/auth/login` · `POST /api/v1/auth/logout` · `GET /api/v1/auth/me` · `GET/POST /api/v1/users` · `GET/PATCH /api/v1/users/{id}` · `PATCH /api/v1/users/{id}/role` · `PATCH /api/v1/users/{id}/password`. Interactive docs at `/api/v1/docs`.

## Run locally
```bash
cp -n .env.example .env; cp -n backend/.env.example backend/.env; cp -n frontend/.env.local.example frontend/.env.local
docker compose up -d --build            # backend applies migrations on start
docker compose exec -e FIRST_ADMIN_EMAIL=admin@cdccmms.com -e FIRST_ADMIN_PASSWORD='<strong>' backend python -m scripts.seed_admin
# backend http://localhost:8100/api/v1/docs · frontend http://localhost:3100
docker compose down                     # stop (volumes persist)
```

## Notes / deviations
- `email-validator` intentionally avoided (regex pattern + DB CHECK) to keep deps lean.
- Login throttle is per `email+IP`, 5 failures / 15-min window, Redis-backed.
- The running stack from this session was left up for inspection; `docker compose down` to stop.
- **Not done (by design):** refresh tokens, password-reset-by-email, SSO/MFA, persistent lockout.

**Awaiting approval to begin V1 Employees (Step 2 of the build order).**
