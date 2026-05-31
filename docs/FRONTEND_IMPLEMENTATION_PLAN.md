# Frontend Implementation Plan

> **Phase:** Frontend build roadmap (no code). Brand-agnostic (codename **CoreOps**; product name = one token, D-001). Confirms the stack and sequences the build. Supersedes two earlier open items: **FD-2 → TanStack Query (confirmed)** and the component approach (**shadcn/ui** instead of porting the bespoke prototype). Aligns with `FRONTEND_ARCHITECTURE.md`, `FRONTEND_DESIGN_SYSTEM.md`, `FRONTEND_ROUTE_MAP.md`, the 6 screen specs, and `api/openapi-v1.yaml`.

---

## 0. Stack (locked)

| Concern | Choice | Role |
|---|---|---|
| Framework | **Next.js (App Router)** | routing, layouts, code-splitting |
| Language | **TypeScript (strict)** | types mirror `openapi-v1.yaml` |
| Styling | **Tailwind CSS** | design tokens as theme; utility styling |
| Components | **shadcn/ui** (Radix + Tailwind) | accessible primitives we own (copied into `components/ui`) |
| Server state | **TanStack Query** | fetch/cache/mutations/invalidation |
| Forms | **React Hook Form** | form state/perf |
| Validation | **Zod** | schema validation (forms + API parsing); RHF resolver |
| Icons | **lucide-react** | matches design system (stroke 1.5) |
| Toast | **shadcn/ui (Sonner)** | transient feedback |
| Tests | **Vitest + Testing Library + MSW + Playwright** | unit/integration/e2e |

**Design-system mapping:** the tokens in `FRONTEND_DESIGN_SYSTEM.md` (slate/blue palette, Inter / Source Serif 4 / Geist Mono, spacing/radii/shadow/motion) become the **Tailwind theme** (CSS variables + `tailwind.config`). This also **closes U-005** — tokens are authored once in the Tailwind theme and consumed by shadcn components. shadcn components are themed to our tokens, not used stock.

> **V0 note:** the current `frontend/` skeleton uses plain `globals.css` and no Tailwind. Phase F0 introduces Tailwind + shadcn and re-homes the landing page; this is an additive foundation change, not a rewrite.

---

## 1. Folder structure (target)

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx                 # root: providers (Query, Auth, Toaster), fonts, globals
│   │   ├── page.tsx                   # redirect → /dashboard | /login
│   │   ├── (auth)/login/page.tsx
│   │   └── (app)/
│   │       ├── layout.tsx             # AppShell + auth guard + role nav
│   │       ├── dashboard/page.tsx
│   │       ├── employees/page.tsx
│   │       ├── employees/[id]/page.tsx
│   │       ├── projects/page.tsx
│   │       ├── projects/[id]/page.tsx
│   │       ├── attendance/page.tsx
│   │       ├── reports/(page|new|[id])/page.tsx
│   │       └── settings/page.tsx
│   ├── components/
│   │   ├── ui/                        # shadcn primitives (button, input, dialog, table, …)
│   │   ├── shell/                     # AppShell, Sidebar, TopNav, PageHeader, Brand
│   │   ├── data/                      # DataTable, Pagination, FilterBar, SearchInput, Toolbar
│   │   └── feedback/                  # EmptyState, ErrorState, Skeletons, ConfirmDialog
│   ├── features/                      # one folder per domain
│   │   ├── auth/                      # api.ts, hooks.ts, schemas.ts, AuthProvider
│   │   ├── users/  employees/  projects/  attendance/  reports/  dashboard/
│   │   │                             #   api.ts (endpoints) · hooks.ts (queries/mutations)
│   │   │                             #   schemas.ts (zod) · components/ (widgets)
│   ├── lib/
│   │   ├── api-client.ts              # fetch wrapper: base URL, JWT, error envelope → AppError
│   │   ├── query-client.ts           # TanStack Query config + keys factory
│   │   ├── rbac.ts                    # can(role, capability)
│   │   ├── format.ts                  # dates, hours, tabular numbers
│   │   └── env.ts                     # typed NEXT_PUBLIC_* access
│   ├── types/  api.ts                 # TS types mirroring openapi-v1.yaml
│   └── styles/  globals.css           # Tailwind base + token CSS variables
├── tailwind.config.ts                 # theme = design tokens
├── components.json                    # shadcn config
├── vitest.config.ts · playwright.config.ts
├── Dockerfile · .env.local.example · package.json · tsconfig.json
```

Per-feature convention: `api.ts` (typed endpoint calls) → `hooks.ts` (TanStack Query wrappers) → `schemas.ts` (Zod) → `components/` (domain widgets). Pages compose feature hooks + shared `components/`.

---

## 2. State management strategy

| State | Tool | Pattern |
|---|---|---|
| **Server data** | TanStack Query | one query key per resource+params via a **keys factory** (`keys.reports.list(filters)`); `staleTime` tuned per resource; mutations call `invalidateQueries` on the affected keys; no manual caching. |
| **Auth/session** | React Context (`AuthProvider`) | `{ user, role, status, login(), logout() }` hydrated from `GET /auth/me`; persisted token (FD-1). |
| **Forms** | React Hook Form + Zod | local to the form; `zodResolver`; submit → mutation. |
| **UI/view state** | `useState` + **URL search params** | tab/filters/search/pagination/month live in the URL → deep-linkable, back-button correct. |
| **Toasts** | Sonner (shadcn) | transient, `aria-live`. |

No Redux/Zustand in v1 (overengineering). Query is the single server-state authority; URL is the single view-state authority.

**Query key conventions:** `['auth','me']`, `['users','list',params]`, `['reports','list',params]`, `['reports','detail',id]`, etc. Mutations invalidate the narrowest keys (e.g. approving a report invalidates `['reports','detail',id]` + `['reports','list']` + `['dashboard','summary']`).

---

## 3. API client architecture

- **`lib/api-client.ts`** — a thin `fetch` wrapper (no axios needed): base URL from `lib/env`, JSON, attaches `Authorization: Bearer <token>` from the auth store, sets/propagates `x-request-id`.
- **Error mapping** — non-2xx → parse the backend envelope `{error:{code,message,details,request_id}}` and throw a typed **`AppError(code, message, status, details)`**. Network/parse failures → `AppError('network_error', …, 0)`.
- **401 handling** — a single place clears the session and redirects to `/login?next=` (no refresh token in v1).
- **Response validation** — Zod-parse responses **at the feature `api.ts` boundary** for critical payloads (auth, lists) so the UI fails loud on contract drift; lightweight elsewhere.
- **TanStack integration** — feature `hooks.ts` wrap `api.ts` calls in `useQuery`/`useMutation`; components never call `fetch` directly.
- **Types** — `types/api.ts` mirrors `openapi-v1.yaml`; Zod schemas in `features/*/schemas.ts` are the runtime counterpart (and can infer the TS types). Codegen from OpenAPI is a later optimization (FD-4 — hand-authored for v1).
- **Pagination contract** — `{items,total,limit,offset}` consumed directly by `DataTable`+`Pagination`.

---

## 4. Auth flow architecture

```
Login form (RHF+Zod) ──POST /auth/login──► token (JWT, 60m, no refresh)
        │                                        │
        ▼                                        ▼
  AuthProvider.login(token) ──► store token (FD-1) ──► GET /auth/me ──► {user,role}
        │
        ▼
 (app)/layout guard:  session? ──no──► /login?next=<path>
                          │yes
                          ▼
                 AppShell + role-aware nav (rbac.can)
```

- **Login** — `(auth)/login` form (RHF + Zod: email pattern, password required) → `useLogin()` mutation → on success store token, prime `['auth','me']`, redirect to `next` or `/dashboard`. Errors: 401 → form-level "Invalid email or password"; 429 → "Too many attempts, try again later" (maps the backend throttle).
- **Session** — `AuthProvider` exposes `user/role/status`; `useAuth()` hook. Token in memory + `localStorage` mirror (FD-1; cookie+CSRF hardening is backlog).
- **Guard** — `(app)/layout.tsx` blocks render until session resolved; unauth → redirect. `<RequireRole roles>` for admin-only areas (Settings → Users) → 403 in-shell.
- **Logout** — `useLogout()` → `POST /auth/logout` (denylists `jti`) → clear token → `/login`.
- **401 anywhere** — api-client triggers the same clear+redirect with a "session expired" toast.
- **RBAC** — `lib/rbac.ts` `can(role, capability)` mirrors `V1_ARCHITECTURE_PACKAGE.md` §7; gates nav, buttons, routes. **Server remains source of truth.**
- **FD-3 gap** — Settings → Security change-password needs a backend `PATCH /auth/me/password` (not in v1 OpenAPI). Until decided, that form is admin-reset-only.

---

## 5. Page build order

Ordered by dependency and **backend readiness** (auth + `/users` are live today; employees/projects/attendance/reports backends are later phases). Each page ships against its real endpoint; where the backend isn't ready, build against **MSW mocks derived from `openapi-v1.yaml`** and switch to live when the endpoint lands.

| # | Page(s) | Backend dep | Notes |
|---|---|---|---|
| **F0** | *Foundation (no page)* | — | Tailwind + shadcn + theme tokens; providers (Query, Auth, Toaster); `api-client`; `rbac`; AppShell + guard |
| **F1** | `/login` | ✅ `/auth/*` live | first real vertical slice end-to-end |
| **F2** | `/dashboard` | ⚠ `/dashboard/summary` later | shell + KPIs; partial/mocked until summary endpoint; recent reports after F6 |
| **F3** | `/settings` (Profile, Users & Roles) | ✅ `/auth/me`, `/users` live | **highest-value early win** — admin user management works against live API now |
| **F4** | `/employees` (+ `/[id]`) | ⏳ employees API | list/detail/CRUD; mock→live |
| **F5** | `/projects` (+ `/[id]`) | ⏳ projects API | cards/table + detail/burn |
| **F6** | `/attendance` | ⏳ attendance API | check-in/out + calendar/history/team |
| **F7** | `/reports` (+ `/new`, `/[id]`) | ⏳ reports API | core loop: file + review |
| **F8** | polish | — | empty/error/loading parity, a11y pass, responsive QA |

> **Recommended first two real pages: F1 Login then F3 Settings/Users** — both are backed by live endpoints, so they validate the entire stack (auth → query → RHF/Zod → table/mutations → RBAC) before the other backends exist.

---

## 6. Component build order

Bottom-up so pages have what they need:

1. **Theme & tokens** — Tailwind theme (colors/fonts/radii/shadow/motion), `globals.css` variables, `Brand` component (`--product-name`).
2. **shadcn primitives** (themed): Button, Input, Textarea, Select, Checkbox, Label, Badge, Avatar, Dialog, DropdownMenu, Tabs, Table, Tooltip, Popover, Skeleton, Sonner(Toast), Command(⌘K), Sheet(mobile drawer), Calendar, Form (RHF wrappers).
3. **Form system** — `Form`/`FormField` (RHF + Zod) + field error display + the uniform-error-to-field mapping.
4. **Data components** — `DataTable` (sort/select/sticky header + empty/loading/error bodies), `Pagination`, `FilterBar`/`FilterChip`, `SearchInput` (debounced), `Toolbar`.
5. **Shell** — `AppShell`, `Sidebar`/`NavItem` (role-gated), `TopNav` (breadcrumbs, search, avatar menu), `PageHeader`.
6. **Feedback** — `EmptyState`, `ErrorState` (retry), `Skeleton` variants, `ConfirmDialog`, KPI tile.
7. **Domain widgets** (per feature, during F4–F7) — status badge maps, project card, attendance calendar cell, report form sidecar, review panel, charts (lightweight SVG).

---

## 7. Testing strategy

| Layer | Tool | Coverage |
|---|---|---|
| **Unit** | Vitest + Testing Library | DS primitives (states/variants), `rbac.can`, `format`, Zod schemas (valid/invalid) |
| **Hooks/data** | Vitest + **MSW** | TanStack Query hooks against mocked `openapi-v1.yaml` responses (success + 401/403/409/422 envelopes) |
| **Forms** | RTL | RHF+Zod validation, submit, server-error→field mapping |
| **Integration** | RTL + MSW | a page renders list → filter → paginate → empty/error states |
| **E2E** | Playwright | journeys: login→dashboard; admin creates user→that user logs in; employee blocked from admin Settings (RBAC negative); (later) submit report→manager review; check-in/out |
| **A11y** | axe (in component/e2e) | focus order, labels, contrast, `aria-live`, keyboard (⌘K/Esc) |
| **Visual (optional)** | Playwright snapshots | key screens desktop + mobile |

- **MSW** lets F2/F4–F7 proceed before their backends exist; the same handlers double as test fixtures.
- **CI**: typecheck + lint + Vitest on PR; Playwright on a built app (compose) pre-merge.
- **Definition of done per page**: real/mocked data wired, empty+loading+error states, RBAC gating, mobile layout, a11y pass, tests green.

---

## 8. Phases (roadmap form)

| Phase | Objective | Key deliverables | Risks | Done when |
|---|---|---|---|---|
| **F0 Foundation** | stack + shell | Tailwind+shadcn theme, providers, api-client, rbac, AppShell+guard, MSW setup | token/theme drift from design system | app boots themed; guard redirects; `/auth/me` hydrates |
| **F1 Login** | auth e2e | login page, AuthProvider, logout, 401 handling | localStorage/XSS (FD-1) | real login→dashboard; logout revokes |
| **F3 Settings/Users** | admin value on live API | profile, users table (list/create/role/password/active), guards | last-admin/self guards UX | admin manages users; RBAC negative paths covered |
| **F2 Dashboard** | home | KPIs + recent (mock→live) | summary endpoint timing | renders scoped KPIs; graceful when summary mocked |
| **F4 Employees** | directory | list/detail/CRUD | backend contract drift | matches `openapi-v1.yaml`; mock→live swap clean |
| **F5 Projects** | catalog+hub | cards/table + detail/burn | — | parity with spec |
| **F6 Attendance** | presence | check-in/out + calendar/history/team | timezone rendering | punches + month views work |
| **F7 Reports** | core loop | list/new/detail + review | edit-lock (409) UX | file→review→approve flow |
| **F8 Polish** | quality | a11y + responsive + states parity | — | WCAG AA pass; mobile QA |

---

## 9. Decisions resolved / still open
- **Resolved:** FD-2 → **TanStack Query**; component approach → **shadcn/ui themed to our tokens**; **U-005** → tokens in Tailwind theme.
- **Open:** **FD-1** token storage (localStorage v1 → cookie+CSRF backlog); **FD-3** self password-change endpoint (needed for Settings→Security — recommend adding `PATCH /auth/me/password`); **FD-4** OpenAPI type codegen (hand-authored for v1).
- **Dependency:** F4–F7 need their backend endpoints (employees/projects/attendance/reports) — build behind MSW until live.

_Related: [`FRONTEND_ARCHITECTURE.md`](./FRONTEND_ARCHITECTURE.md) · [`FRONTEND_DESIGN_SYSTEM.md`](./FRONTEND_DESIGN_SYSTEM.md) · [`FRONTEND_ROUTE_MAP.md`](./FRONTEND_ROUTE_MAP.md) · screen specs · [`api/openapi-v1.yaml`](./api/openapi-v1.yaml)._
