# Frontend F0 + F1 — Completion Report

**Date:** 2026-05-31 · **Branch:** `feature/v1-authentication` · **Scope:** F0 (Foundation) + F1 (Authentication) only. **No** Employees/Projects/Attendance/Reports built. Build + typecheck green.

## Summary
Real production code for the frontend foundation and authentication. Stack per spec: Next.js App Router · TypeScript (strict) · Tailwind · shadcn/ui · TanStack Query · React Hook Form · Zod. Verified with `tsc --noEmit` and `next build` (both pass) and a running server (routes serve).

---

## 1. Files created

**Tooling / theme (F0)**
- `frontend/package.json` (deps + scripts incl. `typecheck`), `package-lock.json`
- `frontend/tailwind.config.ts` (design tokens → Tailwind theme; closes U-005)
- `frontend/postcss.config.js`, `frontend/components.json` (shadcn config)
- `frontend/src/app/globals.css` (Tailwind layers + HSL token variables)

**Lib (F0)**
- `src/lib/utils.ts` (`cn`), `src/lib/env.ts`, `src/lib/auth-storage.ts` (token persistence, FD-1)
- `src/lib/api-client.ts` (typed fetch; JWT attach; **error envelope → `AppError`**)
- `src/lib/query-client.ts` (TanStack Query factory; **centralized 401 → /login**)
- `src/lib/rbac.ts` (`can(role, capability)`)
- `src/types/api.ts` (Role, User, Me, TokenResponse, ApiErrorBody, Page<T>)

**UI primitives — shadcn/ui (F0)**
- `src/components/ui/`: `button`, `input`, `label`, `card`, `form`, `avatar`, `dropdown-menu`, `skeleton`, `separator`, `sonner` (Toaster)

**Shell + feedback (F0)**
- `src/components/shell/`: `brand`, `sidebar`, `top-nav`, `page-header`, `app-shell`
- `src/components/feedback/full-screen-loader.tsx`

**Providers / root (F0)**
- `src/app/providers.tsx` (QueryClient + AuthProvider + Toaster)
- `src/app/layout.tsx` (Inter + Source Serif 4 via `next/font`, providers)
- `src/app/page.tsx` (redirect → /dashboard)

**Auth (F0/F1)**
- `src/features/auth/`: `schemas.ts` (Zod login), `api.ts` (login/logout/me), `auth-provider.tsx` (session context, `/auth/me` hydration), `login-form.tsx` (RHF + Zod)
- `src/app/(auth)/login/page.tsx` (split layout + Suspense)
- `src/app/(app)/layout.tsx` (**route guard**)
- `src/app/(app)/dashboard/page.tsx` (authenticated landing — placeholder for F2)

**Removed:** `src/lib/api.ts`, `src/lib/config.ts` (V0 stubs, superseded).

---

## 2. Dependencies added

**Runtime:** `@tanstack/react-query@5.59`, `react-hook-form@7.53`, `@hookform/resolvers@3.9`, `zod@3.23`, `lucide-react@0.453`, `sonner@1.5`, `class-variance-authority@0.7`, `clsx@2.1`, `tailwind-merge@2.5`, `tailwindcss-animate@1.0.7`, `@radix-ui/react-{slot,label,dropdown-menu,avatar,separator}`.
**Dev:** `tailwindcss@3.4`, `postcss@8.4`, `autoprefixer@10.4`.
**Upgraded:** `next` 14.2.15 → **14.2.35** (security advisory 2025-12-11).

---

## 3. Routes implemented

| Route | Type | Behavior |
|---|---|---|
| `/` | server redirect | → `/dashboard` (guard then handles auth) |
| `/login` | public | RHF+Zod sign-in; maps 401 → "Invalid email or password", 429 → throttle message; redirects to `?next` or `/dashboard`; already-authed → bounce to app |
| `/dashboard` | protected | authenticated landing (greeting + user/role); placeholder for full F2 dashboard |
| `(app)` layout | guard | loading splash while hydrating; unauth → `/login?next=`; renders AppShell |

**Logout:** TopNav avatar menu → `POST /auth/logout` (server denylist) + local token clear → `/login`.
**Session hydration:** AuthProvider runs `GET /auth/me` when a token exists; exposes `{status, user, role}`.

---

## 4. Verification

**Automated (run, passing):**
- `npm run typecheck` (`tsc --noEmit`) → **0 errors**.
- `npm run build` (`next build`) → **success**; routes `/`, `/login`, `/dashboard`, `/_not-found` compiled & prerendered; fonts fetched.
- Local `next start -p 3100`: `GET /login` → **200**, `GET /` → **307** (redirect), `GET /dashboard` → **200**; document `<title>` renders `CoreOps`.
- **Containerized** (`docker compose` frontend, rebuilt): `GET /login` → **200**, `GET /dashboard` → **200**, **0** "module not found", `CoreOps` present. Full stack up (db/redis/backend:8100/frontend:3100).
- Backend integration contract proven in `V1_AUTHENTICATION_REPORT.md` (login → JWT → /me → logout revoke), which is exactly what this UI calls.

**Manual browser steps (to confirm the interactive flow):**
1. `cp -n frontend/.env.local.example frontend/.env.local` (API base → `http://localhost:8100/api/v1`).
2. Ensure backend up (`docker compose up -d --wait db redis backend`) and an admin exists (`docker compose exec -e FIRST_ADMIN_EMAIL=… -e FIRST_ADMIN_PASSWORD=… backend python -m scripts.seed_admin`).
3. Open `http://localhost:3100/login` → sign in with the admin creds → lands on `/dashboard` showing email + role.
4. Avatar menu → **Sign out** → returns to `/login`; revisiting `/dashboard` redirects back to `/login`.
5. Wrong password → inline "Invalid email or password."; 5 quick failures → throttle message (429).

> The login **form body is client-rendered** (Suspense boundary for `useSearchParams`), so it appears in the browser via JS — not in the raw SSR HTML snapshot. This is expected and correct.

---

## 5. Notes & deviations
- **Geist Mono** not loaded as a webfont; `--font-mono` falls back to a system mono stack (numeric data uses Inter `tabular`). Cosmetic; can self-host Geist Mono later.
- **Unbuilt nav items** (Employees/Projects/Attendance/Reports/Analytics/Settings) render **disabled with a "soon" tag** so the shell looks complete without dead links. They activate as their phases land.
- **Token storage** = localStorage (FD-1); httpOnly-cookie+CSRF hardening remains backlog.
- **Docker `frontend` container** had stale `node_modules` (anonymous volume from the old package.json) and was rebuilt so the dev stack resolves the new deps.

---

## 6. Remaining work (next phases — not in F0/F1)
- **F2 Dashboard** (KPIs/recent/charts) — needs `/dashboard/summary` backend.
- **F3 Settings/Users** — buildable now against live `/users`; **needs FD-3 decision** (self password-change endpoint) for the Security tab.
- **F4–F7** Employees/Projects/Attendance/Reports — need their backend endpoints; build behind **MSW** until live.
- **Testing infra** (Vitest + Testing Library + MSW + Playwright) — set up before/with F3.
- **shadcn primitives** still to add for later screens: Table, Tabs, Select, Dialog, Command (⌘K), Sheet, Calendar, Badge, Pagination, Tooltip, Popover.
- **Hardening:** cookie-based auth (FD-1), a11y audit pass, error/empty/loading parity across screens.

**F0 + F1 complete and verified. Awaiting direction for the next phase (F3 Settings/Users is the recommended next, since it runs on live endpoints).**
