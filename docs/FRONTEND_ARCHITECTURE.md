# Frontend Architecture

> **Phase:** Frontend architecture validation (no code). Brand-agnostic (codename **CoreOps**; product name = one token, D-001). Validates and extends the V0 Next.js skeleton before building Employees, Projects, Attendance, Reports. Consistent with `frontenddesign.md`, `V1_ARCHITECTURE_PACKAGE.md`, and `api/openapi-v1.yaml`.

---

## 1. Stack & rendering strategy

- **Next.js (App Router) + TypeScript**, single SPA-style app served by the `frontend` container (host **:3100**). Talks to FastAPI at `NEXT_PUBLIC_API_BASE_URL` (`http://localhost:8100/api/v1`).
- **Rendering model for v1: client-rendered authenticated app.** The authenticated area (`(app)`) is rendered client-side because it is a private, token-gated, data-dense dashboard — SSR/RSC data fetching with a bearer token held client-side adds complexity for no SEO benefit (internal tool, no public pages).
  - **Server Components** used only for static shell/layout chrome that needs no auth.
  - **Client Components** (`"use client"`) for everything that reads the token, fetches data, or holds interaction state (tables, forms, filters).
- **No SSR of private data in v1.** Revisit only if a public surface appears (none planned).

## 2. Folder structure (target)

Extends the V0 skeleton (`frontend/src/...`):

```
src/
├── app/
│   ├── layout.tsx                 # root: providers (Query, Auth, Toast), fonts, globals
│   ├── page.tsx                   # redirect → /dashboard (or /login if unauth)
│   ├── (auth)/login/page.tsx      # public
│   └── (app)/
│       ├── layout.tsx             # AppShell + auth guard + role-aware nav
│       ├── dashboard/page.tsx
│       ├── employees/page.tsx
│       ├── employees/[id]/page.tsx
│       ├── projects/page.tsx
│       ├── projects/[id]/page.tsx
│       ├── attendance/page.tsx
│       ├── reports/page.tsx
│       ├── reports/new/page.tsx
│       ├── reports/[id]/page.tsx
│       └── settings/page.tsx
├── components/
│   ├── ds/                        # design-system primitives (Button, Card, Table, Badge, …)
│   ├── shell/                     # AppShell, Sidebar, TopNav, PageHeader
│   ├── data/                      # DataTable, Pagination, FilterBar, SearchInput, Toolbar
│   └── feedback/                  # EmptyState, ErrorState, Skeletons, Toast
├── features/                      # per-domain hooks + types + small widgets
│   ├── auth/  employees/  projects/  attendance/  reports/  dashboard/  users/
├── lib/
│   ├── api.ts                     # fetch client (JWT attach, error envelope → AppError)
│   ├── auth.ts                    # token storage, session context, login/logout
│   ├── rbac.ts                    # role helpers: can(role, action)
│   ├── query.ts                   # React Query client config
│   └── format.ts                  # dates, hours, tabular numbers
├── styles/  tokens.css            # design tokens (re-authored — U-005)
└── types/  api.ts                 # TS types mirroring openapi-v1.yaml schemas
```

## 3. State management

| State kind | Mechanism | Notes |
|---|---|---|
| **Server state** | **React Query (TanStack Query)** | caching, background refetch, mutations + invalidation. One query key per resource+params. |
| **Auth/session** | small **AuthContext** hydrated from `GET /auth/me` | holds `{user, role, status}`; not heavy global store. |
| **UI state** | local `useState` + **URL query params** | tab, filters, page, search live in the URL → linkable, back-button correct. |
| **Toasts** | Toast context (from the prototype `useToasts`) | transient, bottom-right. |

**No Redux/heavy store** in v1 (overengineering). Introduce only if cross-cutting client state grows.

## 4. Authentication & token handling

- **Login** (`POST /auth/login`) → JWT access token (HS256, 60-min TTL, no refresh in v1 — D-V1-3).
- **Token storage:** in-memory (AuthContext) + mirrored to `localStorage` for reload persistence. *(Trade-off noted: localStorage is XSS-exposed; acceptable for an internal tool in v1. A future hardening is httpOnly cookie + CSRF — tracked as a frontend backlog item.)*
- **Attach:** `lib/api.ts` adds `Authorization: Bearer <token>` to every call.
- **Expiry / 401:** any `401` → clear session, redirect to `/login?next=<path>`. No silent refresh (no refresh token). A lightweight "session expired" toast on redirect.
- **Logout** (`POST /auth/logout`) → server denylists the `jti`; client clears token and redirects to `/login`.

## 5. API consumption

- **One typed client** (`lib/api.ts`): `apiGet/apiPost/apiPatch/apiDelete`, base URL from env, JSON, JWT attach.
- **Error envelope mapping:** backend returns `{error:{code,message,details,request_id}}`. The client throws a typed `AppError(code,message,status,details)`; React Query surfaces it to components, which render the correct state (field errors for 422, toast for transient, full-page for 401/403/404).
- **Pagination contract:** list endpoints return `{items,total,limit,offset}`; the `DataTable`+`Pagination` consume this directly.
- **Types** mirror `openapi-v1.yaml` (hand-authored in `types/api.ts` for v1; codegen optional later).
- **No client-side joins of large data** — request server-filtered/paginated pages.

## 6. Routing & guards

- `(app)/layout.tsx` is the **auth gate**: if no valid session → redirect `/login`. It renders the `AppShell` and the **role-aware sidebar**.
- **Route-level RBAC:** a small `<RequireRole roles={[...]}>` wrapper (or per-page guard) blocks unauthorized roles and renders a 403 state. **Client RBAC is UX only — the API is the source of truth** (every call is authorized server-side; the client just avoids showing dead ends).
- **Deep links** preserve query state; unauthorized deep link → 403 screen, unauthenticated → login with `?next=`.

## 7. RBAC on the client

`lib/rbac.ts` exposes `can(role, capability)` mirroring the API permission matrix (`V1_ARCHITECTURE_PACKAGE.md` §7). Used to:
- show/hide nav items (Employees/Projects mgmt, admin Settings),
- enable/disable action buttons (Create, Review, Approve),
- gate routes.
v1 roles: **admin · manager · employee · viewer** (super_admin/team_lead/recruiter deferred).

## 8. Cross-cutting UI patterns (used by every screen)

- **Loading:** skeletons that match final layout (table rows, KPI tiles, cards) — never a bare spinner for primary content; spinner only for inline actions.
- **Empty:** `EmptyState` (icon + title + one-line description + primary action when the user can act).
- **Error:** inline field errors (422), section-level `ErrorState` with retry (5xx/ network), full-page for 401/403/404.
- **Optimistic where safe:** toggles; **not** for financial/审批 actions (reviews) — those confirm from server.
- **Toasts:** success/info/warning/danger, sentence-case, specific ("Report submitted — 4:32 PM").

## 9. Responsive strategy

- Breakpoint **860px** (from `app.css`). Below it: sidebar → off-canvas drawer + scrim; KPI grid → 2-up; two-column layouts → single column; **tables → card/stacked rows or horizontal scroll with a sticky first column** (per-screen choice documented in each spec).
- Touch targets ≥ 40px; primary actions reachable; charts are fluid SVG.

## 10. Accessibility (target WCAG 2.1 AA)

Semantic HTML (`<button>`, `<table>`, `<nav>`, labelled inputs), visible focus rings (token), keyboard operability (⌘K, Esc closes overlays, arrow-key calendar), `aria-live` for toasts/badges, status conveyed by **text + color** (not color alone), `prefers-reduced-motion` honored. (Closes the a11y gap flagged in `frontenddesign.md` §9.)

## 11. Performance

- Route-level code splitting (App Router default); lazy-load heavy widgets (charts, calendar).
- React Query caching + `staleTime` to avoid refetch storms; prefetch on hover for detail links.
- Avoid large client bundles: chart primitives are lightweight SVG (from the prototype), not a heavy chart lib in v1.

## 12. Testing

- **Component tests** (DS primitives, forms, guards).
- **Journey/e2e (Playwright):** login → dashboard → submit report → check-in → manager review; employees CRUD (admin); RBAC negative paths (employee blocked from admin areas).
- **Contract alignment:** types/fixtures derived from `openapi-v1.yaml`.

## 13. Validation of the V0 skeleton (findings)

| Item | State | Action before screens |
|---|---|---|
| App Router + `@/*` alias + brand token | ✅ present | keep |
| `lib/api.ts`, `lib/config.ts` | ✅ minimal | extend with JWT attach + error mapping + methods |
| Auth context / guard | ❌ not built | add in `(app)/layout.tsx` + `lib/auth.ts` (first screen-phase task) |
| React Query provider | ❌ | add to root layout |
| Design tokens (`colors_and_type.css`) | ⚠️ missing (U-005) | re-author `styles/tokens.css` (see `FRONTEND_DESIGN_SYSTEM.md`) |
| DS components | ⚠️ prototype only (`design-assets`) | port into `components/ds` per phase |
| Route groups `(auth)`/`(app)` | ❌ (single landing page) | restructure now |

**No architectural blockers.** The skeleton is a clean base; the above are additive.

## 14. Open frontend decisions
- **FD-1** Token storage: in-memory+localStorage now vs httpOnly cookie+CSRF later — recommend localStorage for v1, cookie hardening backlog.
- **FD-2** Data layer: **React Query** (recommended) vs hand-rolled fetch hooks.
- **FD-3** Self-service password change: **no `PATCH /auth/me/password` endpoint exists in v1** (`openapi-v1.yaml` only has admin `/users/{id}/password`). Decide: add a self endpoint or keep admin-reset-only for v1 (see `SETTINGS_SCREEN_SPEC.md`).
- **FD-4** Type generation: hand-authored types now vs OpenAPI codegen later.

_Related: [`FRONTEND_DESIGN_SYSTEM.md`](./FRONTEND_DESIGN_SYSTEM.md) · [`FRONTEND_ROUTE_MAP.md`](./FRONTEND_ROUTE_MAP.md) · [`frontenddesign.md`](./frontenddesign.md) · [`api/openapi-v1.yaml`](./api/openapi-v1.yaml)._
