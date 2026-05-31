# Frontend Route Map

> **Phase:** Frontend validation (no code). Brand-agnostic. Defines the v1 route tree, layouts, guards, role visibility, navigation, and URL-state conventions. Aligns with `V1_ARCHITECTURE_PACKAGE.md` §5, `openapi-v1.yaml`, and the v1 RBAC matrix.

---

## 1. Route tree

```
/                                   → redirect: authed → /dashboard, else → /login
(auth)/
  /login                            public            Login (exists; backend ready)
(app)/                              ← auth guard + AppShell
  /dashboard                        all roles         KPIs scoped self/team/org
  /employees                        admin, manager, viewer (employee: self only)
  /employees/[id]                   admin, manager(team), self
  /projects                         all (read); admin (CRUD)
  /projects/[id]                    all (read)
  /attendance                       all (self); manager/admin (team/all)
  /reports                          all (self); manager/admin (team/all)
  /reports/new                      employee+ (author)
  /reports/[id]                     owner; manager/admin (review)
  /settings                         all (profile/prefs); admin (users & roles tab)
*                                   → 404 NotFound (in-shell)
```

## 2. Layouts & groups
- **Root layout** (`app/layout.tsx`): providers (React Query, Auth, Toast), fonts, `tokens.css`, `<Brand/>`.
- **`(auth)` group**: bare centered layout (login split-panel); no shell, no guard.
- **`(app)` group** (`(app)/layout.tsx`): **auth guard** (redirect `/login?next=` if no valid session) + **AppShell** (role-aware sidebar + topnav). All authenticated screens nest here.

## 3. Navigation (role-gated sidebar)

```
WORKSPACE
  Home            /dashboard      all
  Employees       /employees      admin, manager, viewer        (employee: profile link only)
  Projects        /projects       all
  Attendance      /attendance     all
  Reports         /reports        all
MANAGE                            (shown only to manager/admin)
  Settings        /settings       admin (full) · all (profile via avatar menu)
```
- TopNav: breadcrumbs · ⌘K search · notifications bell (deferred backend; UI placeholder) · help · avatar menu (Profile, Settings, Sign out).
- Count badges where relevant (e.g. Reports pending review for managers).

## 4. Role visibility matrix (nav + route)

| Route | admin | manager | employee | viewer |
|---|:--:|:--:|:--:|:--:|
| /dashboard | ✓ | ✓ | ✓ | ✓ |
| /employees (list) | ✓ | ✓ (team) | self only | ✓ (read) |
| /employees/[id] | ✓ | ✓ (team) | self | ✓ (read) |
| /projects, /projects/[id] | ✓ | ✓ (read) | ✓ (read) | ✓ (read) |
| /attendance | ✓ (all) | ✓ (team) | ✓ (self) | ✓ (read) |
| /reports | ✓ (all) | ✓ (team) | ✓ (self) | ✓ (read) |
| /reports/new | ✓ | ✓ | ✓ | — |
| /reports/[id] (review) | ✓ | ✓ (team) | own (read) | — |
| /settings → Profile/Prefs | ✓ | ✓ | ✓ | ✓ |
| /settings → Users & Roles | ✓ | — | — | — |

Unauthorized role on a route → **403 in-shell state**; unauthenticated → `/login?next=`.

## 5. URL-state conventions (deep-linkable)
- Tabs: `?tab=calendar` · Filters: `?status=submitted&project=<id>&from=2026-05-01&to=2026-05-31` · Search: `?q=...` · Pagination: `?limit=20&offset=40` · Calendar month: `?month=2026-05`.
- Detail routes use the resource UUID. Back/forward and refresh preserve view.

## 6. Redirects & guards
- `/` → `/dashboard` (authed) / `/login` (guest).
- `401` from any call → clear session → `/login?next=<current>` + "session expired" toast.
- `/login` while authed → `/dashboard`.
- After login → `next` param or `/dashboard`.

## 7. Breadcrumbs (examples)
`Workspace / Home` · `Workspace / Employees / Priya Ramanujan` · `Workspace / Projects / WT-WEB-14` · `Workspace / Reports / May 24 — daily` · `Manage / Settings`.

_Related: [`FRONTEND_ARCHITECTURE.md`](./FRONTEND_ARCHITECTURE.md) · screen specs (Dashboard, Employees, Projects, Attendance, Reports, Settings)._
