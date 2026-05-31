# Security Audit — CoreOps WMS (v1)

**Date:** 2026-05-31 · **Scope:** backend (FastAPI), frontend (Next.js), and the Docker deployment artifacts on `feature/v1-authentication`. **Review only — no code modified.** Lens: **production deployment risk.**

> **Headline:** the **application security core is strong** (auth, RBAC, query safety, validation). The material risk is **deployment/infrastructure posture** — the only orchestration artifact is a **development** `docker-compose.yml` (dev servers, root containers, unauthenticated Redis, exposed datastores, weak default creds). **Not production-ready as shipped; the app code largely is.**

---

## 1. Findings

Severity: 🔴 Critical · 🟠 High · 🟡 Medium · 🔵 Low · ⚪ Info. IDs are stable.

### 🔴 Critical

**C1 — `SECRET_KEY` guard fails open on misconfiguration** (`core/config.py`)
The strong-secret check only runs when `ENV != "local"`, and `ENV` **defaults to `"local"`**. A production deploy that forgets to set `ENV` runs with the **default signing key `change-me-in-production`** → anyone can **forge valid admin JWTs** and bypass all authn/authz.
**Fix:** fail closed — require an explicit non-default `SECRET_KEY` unless `ENV` is *explicitly* `local`/`test`; better, drop the default and make `SECRET_KEY` mandatory (no default) so the app refuses to boot without it.

**C2 — Unauthenticated Redis, exposed datastores** (`docker-compose.yml`)
Redis runs with **no password/ACL** and is published to the host on **`0.0.0.0:6381`**; Postgres on `0.0.0.0:5433`. Redis holds the **JWT revocation denylist** and **login-throttle counters** — anyone with host/network reach can `FLUSHALL` (un-revoke logged-out tokens, reset throttles), read `jti`s, or DoS. Postgres is reachable with the default creds (C4).
**Fix (prod):** set Redis `requirepass`/ACL + TLS; **do not publish** db/redis ports (keep them on the internal `wms_net` only), or bind to `127.0.0.1`. Same for Postgres.

**C3 — Production would run development servers** (`docker-compose.yml`, Dockerfiles)
Backend container runs `uvicorn … --reload` (dev autoreload) and the **frontend runs `next dev`** — neither is for production (reloader code execution surface, no optimization, verbose errors). There is **no production compose / build-and-serve path**.
**Fix:** add `docker-compose.prod.yml`: backend `uvicorn`/`gunicorn` workers **without `--reload`**; frontend `next build` + `next start` (or static export) behind the reverse proxy.

### 🟠 High

**H1 — Containers run as root** (`backend/Dockerfile`, `frontend/Dockerfile`)
No `USER` directive → processes run as UID 0; a code-exec bug becomes container-root, worsening breakout impact.
**Fix:** add a non-root user in both images and `USER app`.

**H2 — Weak default credentials** (`docker-compose.yml`, `*.env.example`)
Postgres default `wms:wms`; `SECRET_KEY`/passwords are placeholders. Safe only if every env var is overridden in prod — easy to miss (see C1).
**Fix:** generate strong secrets per environment; never rely on defaults; consider a secrets manager.

**H3 — No TLS enforcement / no reverse proxy provisioned**
The app serves plain HTTP; bearer tokens + credentials travel in cleartext unless a correctly configured TLS proxy fronts it (the planned nginx subdomain isn't built). No HSTS.
**Fix:** terminate TLS at nginx, redirect 80→443, HSTS; never expose the app over plain HTTP in prod.

**H4 — JWT in `localStorage`** (`frontend/lib/auth-storage.ts`)
Access tokens in `localStorage` are exfiltratable by any XSS; combined with no CSP (M2) this is the main client risk. (Known trade-off, FD-1.)
**Fix (hardening):** httpOnly, `Secure`, `SameSite` cookie + CSRF token; add a strict CSP.

**H5 — No global rate limiting or request-size limits**
Only a per-(email+IP) login throttle exists. No IP-wide throttle, no cap on request body size, no limit on expensive endpoints → credential-stuffing across many emails, large-payload abuse, scraping, DoS.
**Fix:** rate limiting at the proxy/app (per-IP global + per-route), and a max body size.

### 🟡 Medium

| ID | Finding | Fix |
|---|---|---|
| **M1** | **Swagger UI + `openapi.json` exposed unauthenticated** (`/api/v1/docs`, `/openapi.json`). API surface disclosure in prod. | Disable docs in prod, or gate behind auth. |
| **M2** | **No security headers** (HSTS, CSP, `X-Content-Type-Options`, `X-Frame-Options`/frame-ancestors, `Referrer-Policy`). | Add via nginx or a middleware. |
| **M3** | **Login throttle keys on client IP** (`request.client.host`). Behind a proxy that's the proxy IP (all users share it) unless `X-Forwarded-For` is parsed from a *trusted* proxy → wrong throttle/audit IP, mass-lockout or weak throttling. | Parse `X-Forwarded-For` only from trusted proxies; add IP-wide throttle. |
| **M4** | **Timing user-enumeration on login** — bcrypt runs only for existing users, so response time leaks account existence (message is correctly generic). | Always run a dummy bcrypt compare for unknown users. |
| **M5** | **No audit log** (decided out of v1). Enterprise/compliance needs who-did-what; `created_by/updated_by` exist but no immutable trail. | Add the designed `audit_logs` (append-only) before enterprise GA. |
| **M6** | **No max-length on free-text fields** (name, description, remarks, client…) and no app-level body cap → storage growth / DoS. | Add `max_length` to schemas; cap body size at the proxy. |
| **M7** | **JWT decode doesn't `require` claims** — `exp` is present because we issue it, but defense-in-depth should enforce `require=["exp"]` and validate `iat`/`nbf`. | `jwt.decode(..., options={"require":["exp","iat","sub","jti"]})`. |
| **M8** | **CORS `allow_credentials=True` with `allow_methods/headers=["*"]`** — unnecessary for bearer auth and dangerous if `CORS_ORIGINS` is ever broadened. | Set `allow_credentials=False` (bearer header doesn't need it); keep an explicit origin allow-list. |

### 🔵 Low / ⚪ Info

| ID | Finding |
|---|---|
| L1 | No refresh tokens; 60-min access token (re-login). Acceptable for v1. |
| L2 | No MFA (out of v1 scope). |
| L3 | Account lockout is Redis-only (soft); a Redis flush resets it (ties to C2). |
| L4 | Error envelope reflects the client-supplied `x-request-id` header (cosmetic). |
| L5 | No dependency vulnerability scanning / SBOM in CI (versions are pinned; Next.js already patched to 14.2.35). |
| L6 | Single uvicorn worker (performance, not security). |
| L7 | `/health/ready` (unauth) reveals DB/Redis up/down — minor recon. |

---

## 2. Strengths (verified — credit where due)

- **Password hashing:** bcrypt **cost 12**, 72-byte guard, **constant-time** `checkpw`; no passlib.
- **JWT:** HS256 with a **fixed algorithm list** (no alg-confusion), signature + `exp` verified by PyJWT; `jti` for revocation.
- **Authorization is DB-authoritative:** `get_current_user` loads the **fresh** user every request and checks `is_active` + `deleted_at`; **the JWT `role` claim is not trusted** for authz — role changes/deactivation take effect immediately.
- **RBAC defense-in-depth:** enforced in the **service layer** *and* the router (`require_role`); **row-level scoping** (`_assert_can_read`, team/own scoping) prevents IDOR across employees/projects/attendance.
- **No SQL injection:** SQLAlchemy ORM throughout; `ILIKE` search values are **bound parameters** (the `%` wrapping is Python-side, the value is parameterized); no raw string-interpolated SQL.
- **No mass assignment:** pydantic schemas restrict writable fields (e.g., employee create can't set role; user update can't set password; attendance can't set computed minutes); server sets `created_by/updated_by`.
- **Input validation:** typed pydantic models, email regex, enum-constrained statuses, **pagination capped at 100**, date/transition/duplicate checks.
- **Token revocation** works (Redis denylist, self-expiring TTL); **logout** is effective.
- **Error handling:** uniform envelope + **catch-all 500 with no stack-trace leak**; validation errors run through `jsonable_encoder`.
- **Secrets hygiene:** real `.env` files git-ignored, only `*.example` committed; verified via `git check-ignore`.
- **Generated-types + contract** keep the frontend honest; `.next` isolation prevents build-artifact clobber.

---

## 3. Recommended fixes — prioritized

**Must-fix before any production exposure (blockers):**
1. **C1** — make `SECRET_KEY` mandatory / fail-closed; require explicit `ENV`.
2. **C2** — Redis auth + TLS; **stop publishing** db/redis ports (internal network only).
3. **C3** — production compose with non-reload backend workers + `next build`/`start`.
4. **H3** — TLS-terminating reverse proxy (HSTS, 80→443).
5. **H2** — strong per-environment secrets/credentials (no defaults).

**High priority (before enterprise GA):**
6. **H1** non-root containers · **H4** cookie-based tokens + CSP · **H5** rate limiting + body caps · **M2** security headers · **M1** disable prod docs.

**Then:** M3 (trusted proxy IP), M4 (dummy hash), **M5 audit log**, M6 (max-lengths), M7 (JWT `require`), M8 (CORS credentials), L5 (CI dep scanning), MFA/refresh-tokens (roadmap).

---

## 4. Enterprise readiness score

**58 / 100 — "Strong app core; not production-ready until deployment is hardened."**

| Domain | Score | Notes |
|---|---:|---|
| AuthN (JWT, hashing, revocation) | 8 / 10 | Solid; fail-open secret (C1), localStorage (H4), no MFA. |
| AuthZ / RBAC | 9 / 10 | Service-layer + row-scoping, DB-authoritative roles — excellent. |
| Input validation & query safety | 9 / 10 | ORM-parameterized, pydantic, capped pagination; add max-lengths. |
| Secrets management | 4 / 10 | Good git hygiene; fail-open default secret + weak defaults. |
| Network & transport | 3 / 10 | No TLS provisioned; db/redis exposed; unauth Redis. |
| Container/runtime hardening | 3 / 10 | Root containers, dev servers, no prod compose. |
| Rate limiting / DoS | 4 / 10 | Login throttle only; no global limits/body caps. |
| Observability / audit | 3 / 10 | No audit log; no dep scanning; request-id tracing only. |
| Headers / browser hardening | 3 / 10 | No CSP/HSTS/security headers. |
| Error handling / info disclosure | 8 / 10 | Uniform envelope, no stack leaks; docs exposed (M1). |

**Interpretation:** the **code** would score ~8/10; the **deployment** drags the system down. None of the blockers are deep rewrites — they're configuration/ops hardening (prod compose, secrets, Redis auth, TLS, non-root). Address C1–C3 + H2–H3 and the score moves into the low-80s; add H1/H4/H5/M1/M2/M5 for enterprise GA.

---

_Review only — no code changed. Related: [`backenddesign.md`](./backenddesign.md) §9/§12, [`architecture.md`](./architecture.md) §9, [`decisions.md`](./decisions.md) (FD-1, audit/U-012), [`V1_ARCHITECTURE_PACKAGE.md`](./V1_ARCHITECTURE_PACKAGE.md)._
