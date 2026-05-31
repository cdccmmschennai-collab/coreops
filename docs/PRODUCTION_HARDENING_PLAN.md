# Production Hardening — Implementation Plan

**Date:** 2026-05-31 · **Status:** plan only — **no code modified.** Source: `SECURITY_AUDIT.md` (C1, C2, C3, H2, H3). Lens: make the system safe to deploy **without disrupting the local-dev workflow**.

> **Guiding principle:** keep the existing `docker-compose.yml` as the **dev** stack (unchanged behavior), and add a separate, hardened **production** path (`docker-compose.prod.yml` + `nginx` + prod env). Application code changes are minimal and **fail-closed by default**.

---

## 0. Master change set (every file touched)

| Finding | File | New? | Change (one line) |
|---|---|---|---|
| C1 | `backend/app/core/config.py` | edit | Default `ENV` → `production`; all-list `ENV`; secret guard now fires unless explicitly local/test |
| C1 | `backend/tests/conftest.py` | edit (if secret made mandatory) | ensure `ENV=test`/`SECRET_KEY` set for the test process |
| C1/H2 | `backend/.env.example` | edit | document `ENV`, strong-`SECRET_KEY` generation; mark creds as placeholders |
| C2 | `docker-compose.yml` (dev) | edit | bind `db`/`redis` host ports to `127.0.0.1`; optional `redis --requirepass` |
| C2/C3/H2/H3 | `docker-compose.prod.yml` | **new** | hardened prod stack: no published db/redis ports, redis auth, prod commands, nginx |
| C2 | `backend/.env.example` + prod env | edit/new | `REDIS_PASSWORD`; `REDIS_URL`/`CELERY_BROKER_URL` include auth |
| C3 | `frontend/next.config.js` | edit | `output: "standalone"` for a lean prod image |
| C3 | `frontend/Dockerfile` | edit | add a multi-stage **`runner`** target (`next build` → `next start`/standalone) |
| C3 | `backend/requirements.txt` | edit (optional) | add `gunicorn` if using gunicorn+uvicorn workers |
| H2 | `docker-compose.prod.yml`, `.env.prod.example` | new | no `:-default` fallbacks; all secrets required from env |
| H2 | `.env.example` (root) | edit | mark every value a placeholder; add generation notes |
| H3 | `deploy/nginx/wms.conf` | **new** | TLS termination, HSTS, security headers, 80→443, proxy `/`→frontend, `/api`→backend |
| H3 | `docker-compose.prod.yml` | new | `nginx` service (only it publishes 80/443); certs volume |
| H3 | `backend` prod command | new (in prod compose) | `uvicorn --proxy-headers --forwarded-allow-ips=…` so client IP/scheme are correct (also fixes M3) |
| H3 | prod env | new | `CORS_ORIGINS=https://<prod-domain>`; `NEXT_PUBLIC_API_BASE_URL=https://<prod-domain>/api/v1` |

> Net new files: `docker-compose.prod.yml`, `.env.prod.example`, `deploy/nginx/wms.conf` (+ optional `frontend/Dockerfile` prod stage, `backend` gunicorn dep). Net edits: `config.py`, `next.config.js`, `frontend/Dockerfile`, `docker-compose.yml`, env examples, `conftest.py` (only if secret made strictly mandatory).

---

## C1 — `SECRET_KEY` fail-closed

**Files:** `backend/app/core/config.py` (+ `backend/.env.example`; `conftest.py` only if removing the default entirely).

**Change:** the root cause is `ENV` defaulting to `local`, so the existing strong-secret guard never fires on a misconfigured prod. Flip the **default `ENV` to `production`** and add an `ENV` allow-list (`local|test|staging|production`). Now an unset/typo'd `ENV` is treated as production → the existing guard rejects the default/weak `SECRET_KEY` and the app **refuses to boot**. (Optional defense-in-depth: drop the `SECRET_KEY` default so it's a required field — this also forces `conftest.py`/CI to set it.)

**Expected impact:** dev unaffected (dev `backend/.env` and `conftest` already set `ENV=local`/`test`). Any non-local process **must** provide a strong `SECRET_KEY` or it won't start — that's the intended fail-closed behavior.

**Risk:** 🟡 Medium — a deploy that already relied on the insecure default will now fail to boot (desired, but coordinate). Tiny chance of breaking CI if `ENV` not set there → set `ENV=test` in CI.

**Rollback:** `git revert` the `config.py` commit (one file). No data/infra impact.

**Verify:**
```bash
# boots in local
ENV=local SECRET_KEY=x python -c "from app.core.config import settings; print(settings.ENV)"
# refuses weak secret when not local (expect a ValueError on import)
ENV=production SECRET_KEY=change-me-in-production python -c "import app.core.config" ; echo "exit=$?"  # non-zero
# unset ENV now defaults to production → also refuses weak secret
SECRET_KEY=change-me-in-production python -c "import app.core.config" ; echo "exit=$?"  # non-zero
# tests still pass
docker compose run --rm --no-deps --entrypoint pytest backend -q
```

---

## C2 — Redis authentication & network isolation

**Files:** `docker-compose.prod.yml` (new), `docker-compose.yml` (dev: bind to localhost), `backend/.env.example` + `.env.prod.example`, (config already reads `REDIS_URL`).

**Change:**
- **Prod:** Redis runs `redis-server --requirepass ${REDIS_PASSWORD}` (or ACL); `REDIS_URL`/`CELERY_BROKER_URL` become `redis://:${REDIS_PASSWORD}@redis:6379/0`. **Do not publish** `db`/`redis` ports — they stay on the internal `wms_net` only.
- **Dev:** bind published ports to `127.0.0.1` (`127.0.0.1:5433:5432`, `127.0.0.1:6381:6379`) so they aren't on `0.0.0.0`; optional dev `requirepass`.
- App needs no code change (`redis.from_url` handles the password in the URL); confirm the denylist/throttle still work.

**Expected impact:** prod Redis/Postgres unreachable from outside the compose network; tokens/throttle data protected. Local dev still reachable on `127.0.0.1` only.

**Risk:** 🟠 High (operational) — a wrong `REDIS_URL`/password breaks login throttle + token revocation + readiness. Mitigated by staged rollout + the verification below.

**Rollback:** prod is a separate compose; revert to the prior image/compose. Redis password is config, not data — changing it doesn't lose data (denylist is ephemeral anyway).

**Verify:**
```bash
# unauthenticated access is refused
docker compose -f docker-compose.prod.yml exec redis redis-cli ping            # (no auth) -> NOAUTH error
docker compose -f docker-compose.prod.yml exec redis redis-cli -a "$REDIS_PASSWORD" ping  # -> PONG
# db/redis NOT published on host
ss -ltnp | grep -E ':5433|:6381' && echo "STILL EXPOSED (bad)" || echo "not exposed (good)"
# app health/readiness still green (denylist reachable)
curl -s localhost:8100/api/v1/health/ready    # {"status":"ok","checks":{"db":"ok","redis":"ok"}}
# logout still revokes (login -> me 200 -> logout 204 -> me 401)
```

---

## C3 — Production runtime (no dev servers)

**Files:** `docker-compose.prod.yml` (new), `frontend/next.config.js` (`output:"standalone"`), `frontend/Dockerfile` (multi-stage `runner`), `backend/requirements.txt` (optional `gunicorn`).

**Change:**
- **Backend (prod):** run `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-4}` **without `--reload`** (or `gunicorn -k uvicorn.workers.UvicornWorker -w 4`). Migrations still via the entrypoint (`alembic upgrade head`). No bind-mount of source in prod (use the built image).
- **Frontend (prod):** multi-stage Dockerfile — `deps` → `build` (`next build`) → `runner` running `next start` (or the standalone server). `next.config.js` `output:"standalone"` shrinks the runner image. No `next dev`, no `/app/.next` bind mount in prod.
- Neither app publishes host ports in prod — only nginx does (H3).

**Expected impact:** prod runs optimized, no autoreload code path, faster + smaller; dev compose still uses `next dev`/`--reload`.

**Risk:** 🟡 Medium — first real prod build of the frontend may surface SSR/build-only issues (none expected; host `next build` already passes). Standalone output path must be wired correctly in the Dockerfile.

**Rollback:** separate prod compose/images; redeploy previous image tag. Dev unchanged.

**Verify:**
```bash
docker compose -f docker-compose.prod.yml build backend frontend
docker compose -f docker-compose.prod.yml up -d
# no dev server markers
docker compose -f docker-compose.prod.yml exec backend sh -c 'ps aux | grep -c "[-]-reload"'   # 0
docker compose -f docker-compose.prod.yml logs frontend | grep -i "next start\|Ready"            # prod server
# app responds (through nginx once H3 is in)
curl -sk https://localhost/api/v1/health        # {"status":"ok"}
```

---

## H2 — Remove weak defaults

**Files:** `docker-compose.prod.yml` + `.env.prod.example` (no `:-` fallbacks; require `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `SECRET_KEY`), `backend/.env.example` + root `.env.example` (mark placeholders, add generation notes), `config.py` (covered by C1; optionally drop dev-cred defaults for non-local).

**Change:** in the **prod** compose, reference `${POSTGRES_PASSWORD:?set me}` (compose's required-variable syntax) so it **errors if unset** — no silent `wms:wms`. `.env.prod.example` documents `openssl rand -base64 48` for secrets. Dev compose keeps friendly defaults (local only, now bound to localhost).

**Expected impact:** prod cannot start without strong, explicit credentials. Dev unchanged.

**Risk:** 🔵 Low — config-only; failure mode is "won't start until you set secrets" (desired).

**Rollback:** `git revert`; dev path untouched.

**Verify:**
```bash
# missing secret -> compose refuses
docker compose -f docker-compose.prod.yml config >/dev/null   # errors listing required vars when unset
grep -R "wms:wms\|change-me-in-production" docker-compose.prod.yml .env.prod.example || echo "no weak defaults in prod"
```

---

## H3 — TLS / reverse-proxy production architecture

**Files:** `deploy/nginx/wms.conf` (new), `docker-compose.prod.yml` (add `nginx` + certs volume), prod env (`CORS_ORIGINS`, `NEXT_PUBLIC_API_BASE_URL` → https origin), backend prod command (`--proxy-headers --forwarded-allow-ips`).

**Change:** add an `nginx` service that is the **only** thing publishing `80`/`443`. It terminates TLS, redirects 80→443, sets **HSTS + security headers** (`X-Content-Type-Options`, `X-Frame-Options`/`frame-ancestors`, `Referrer-Policy`, a baseline CSP), and reverse-proxies `/` → `frontend:3000` and `/api` → `backend:8000` over the internal network. Certs via certbot/Let's Encrypt (volume-mounted) or provided certs. Backend runs with `--proxy-headers` + a trusted `--forwarded-allow-ips` so client IP/scheme are correct (also resolves **M3**). `CORS_ORIGINS` set to the single https origin; `allow_credentials` can be turned off (M8).

**Expected impact:** all traffic is HTTPS with HSTS + headers; app/db/redis ports are internal-only; correct client IPs for throttling/audit.

**Risk:** 🟠 High (operational) — TLS/cert/proxy misconfig can take the site down or mis-set headers; CSP can break the SPA if too strict. Mitigate: stage on a test domain, start with report-only CSP, verify before cutover.

**Rollback:** nginx is a front door — revert the compose/nginx config and redeploy; or temporarily route directly to the app. Cert renewal is independent.

**Verify:**
```bash
curl -sI https://<domain>/ | grep -i "strict-transport-security\|x-frame-options\|x-content-type-options"
curl -sI http://<domain>/ | grep -i "location: https"      # 80 -> 443 redirect
curl -sk https://<domain>/api/v1/health                    # {"status":"ok"} via proxy
ss -ltnp | grep -E ':80|:443' && ! ss -ltnp | grep -E ':5433|:6381|:8100|:3100'  # only proxy exposed
nginx -t                                                    # config valid (in the nginx container)
```

---

## Implementation order (safest first)

1. **C1** (`config.py`) — pure code, fail-closed default; smallest blast radius. *(Confirm tests green; this gates everything else being safe to deploy.)*
2. **H2** (prod env + `.env.prod.example`, mark placeholders) — prepares strong secrets the next steps consume.
3. **C2** (Redis auth + isolation; dev port binding to localhost) — protects tokens/throttle; needed before any external exposure.
4. **C3** (`docker-compose.prod.yml`, frontend standalone, backend workers) — real prod runtime, still internal-only.
5. **H3** (nginx TLS + headers; flip CORS/API origin) — front door **last**, once a hardened internal stack exists.

*Rationale:* each step is safe to land independently; nothing external is exposed until the final step, and the dev workflow is never broken (separate prod compose).

---

## Global rollback strategy

- **Additivity:** prod lives in **new files** (`docker-compose.prod.yml`, `deploy/nginx/`, `.env.prod.example`, optional `Dockerfile` prod stage). The only behavioral code edit is `config.py` (C1) — single-file `git revert`.
- **Per-step git commits** (small) so any step reverts independently.
- **Image tags:** build prod images with version tags; rollback = redeploy the previous tag.
- **Dev untouched:** `docker-compose.yml` keeps working for local dev throughout; worst case, operate via dev compose while fixing prod.
- **Stateless secrets:** Redis denylist/throttle are ephemeral; rotating `REDIS_PASSWORD`/`SECRET_KEY` loses no business data (existing sessions invalidate — acceptable/known).
- **DB safety:** no schema changes in this plan; `pg_dump` before any prod cutover regardless.

## Risk register (summary)

| Change | Risk | Primary failure mode | Mitigation |
|---|---|---|---|
| C1 config | 🟡 Med | App refuses to boot if secret unset (desired) | set `ENV`/`SECRET_KEY` in CI + prod env first |
| H2 defaults | 🔵 Low | Prod won't start without secrets (desired) | `.env.prod.example` + `config` validation |
| C2 Redis | 🟠 High | Wrong `REDIS_URL` breaks revocation/throttle | readiness check + logout test before cutover |
| C3 runtime | 🟡 Med | Frontend prod-build/standalone wiring | build + smoke on staging first |
| H3 nginx/TLS | 🟠 High | TLS/CSP misconfig → outage/broken SPA | test domain, report-only CSP, header verify |

---

## Out of scope (separate follow-ups, not in this plan)
H1 non-root containers, H4 cookie-based tokens + full CSP, H5 app-level rate limiting/body caps, M1 disable prod docs, M4 dummy-hash, **M5 audit log**, M6 max-lengths, M7 JWT `require`, L5 CI dependency scanning, MFA/refresh tokens. (H3's nginx delivers the M2 security headers and M3 client-IP fix as a side effect.)

_Planning only — no code changed. Related: [`SECURITY_AUDIT.md`](./SECURITY_AUDIT.md) · [`architecture.md`](./architecture.md) §8/§9 · [`V1_ARCHITECTURE_PACKAGE.md`](./V1_ARCHITECTURE_PACKAGE.md) §9._
