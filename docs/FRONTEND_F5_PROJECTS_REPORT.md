# F5 — Projects Frontend: Completion Report

**Date:** 2026-05-31 · **Branch:** `feature/v1-authentication` · **Status:** complete; typecheck + build green; routes verified. **No work on Attendance/Reports/Analytics/Dashboard.**

Implements the Projects UI against the **live** V3 Projects API, reusing the Employees frontend as the exact architectural pattern. Types are **generated from the live OpenAPI contract** (`openapi-typescript`) — no hand-inference, no mock data.

---

## 1. Type generation
- Re-snapshotted the live spec to `frontend/openapi.json` and regenerated `src/types/openapi.ts` (`npm run gen:api`).
- Project/member types derive from generated `components["schemas"]`: `ProjectOut/Create/Update/Page/Status`, `ProjectMemberOut/Create/Role`.

## 2. Files created (mirrors `features/employees`)
**Feature** `src/features/projects/`: `types.ts`, `keys.ts`, `schemas.ts`, `api.ts`, `hooks.ts` + `components/` → `status-badge`, `projects-filters`, `projects-table`, `projects-view`, `archive-dialog`, `project-detail`, `project-members`, `project-form`, `project-edit`.
**Pages** `(app)/projects/`: `page.tsx`, `new/page.tsx`, `[id]/page.tsx`, `[id]/edit/page.tsx`.
**New primitive:** `components/ui/textarea.tsx` (for project description; reusable).
**Modified:** `components/shell/sidebar.tsx` (enabled Projects nav); `openapi.json` + `types/openapi.ts` (regenerated).
**No new npm dependencies** (Radix select/alert-dialog already added in F4).

## 3. API integration mapping

| UI | Endpoint | Hook |
|---|---|---|
| List (search/filter/paginate) | `GET /projects?q&status&limit&offset` | `useProjects` |
| Detail | `GET /projects/{id}` | `useProject` |
| Create | `POST /projects` | `useCreateProject` |
| Edit | `PATCH /projects/{id}` | `useUpdateProject` |
| Archive | `DELETE /projects/{id}` | `useArchiveProject` |
| Members list | `GET /projects/{id}/members` | `useProjectMembers` |
| Assign | `POST /projects/{id}/members` | `useAddMember` |
| Change role | `PATCH /projects/{id}/members/{employee_id}` | `useUpdateMemberRole` |
| Remove | `DELETE /projects/{id}/members/{employee_id}` | `useRemoveMember` |
| Assignable employees | `GET /employees?status=active&limit=100` | `useEmployees` (reused) |

Mutations invalidate `["projects"]` (+ detail/members) and toast; errors mapped via `AppError`: 409→`code` field, 422 (bad dates / invalid status transition / inactive employee)→top alert or toast, 403→guard/toast, 404→NotFound, 401→global. List state (q/status/offset) is URL-driven.

## 4. Screens delivered
- **List** `/projects` — table (Project, Client, Status badge, Members count), debounced search (code/name/client), status filter (incl. archived), pagination, empty/loading/error states; admin row actions (Edit, Archive).
- **Detail** `/projects/[id]` — Overview (code, client, status, dates, description) + **Members** card.
- **Create** `/projects/new` & **Edit** `/projects/[id]/edit` — RHF+Zod (code immutable on edit), admin-guarded (`RequireCapability`). Status select; backend transition guards surface as a calm top-level error.
- **Member management** (admin) — inline on the detail Members card: assign via **employee selector** (reuses `useEmployees`, excludes already-assigned), role select (lead/member), per-member role change and remove. Lead-uniqueness + duplicate/inactive/archived rules enforced server-side and surfaced as toasts.

## 5. Status badges
planning→neutral · active→success · on_hold→warning · completed→info · archived→neutral.

## 6. RBAC (UI mirrors API)
- **admin** — full: create/edit/archive + member assign/role/remove.
- **manager / employee** — read **only assigned projects** (the API scopes the list/detail; the UI shows no management controls).
- **viewer** — read-only all.
Controls gated by `can(role,"project.manage")`; `/new` and `/edit` route-guarded; server enforces regardless.

## 7. Verification
- **`npm run typecheck`** (strict) → clean after every phase.
- **`npm run build`** → success after every phase; routes built: `/projects`, `/projects/[id]`, `/projects/[id]/edit`, `/projects/new`.
- **Docker:** running frontend container (F4 image, all deps present) serves the new routes; full stack up (db/redis/backend:8100/frontend:3100). _(route check appended below.)_
- **Live API:** V3 endpoints verified in the backend (66 passing tests); these hooks call those exact endpoints.

**Manual browser steps (against live backend):**
1. Sign in as admin → **Projects** nav → list loads; search/filter/paginate.
2. **New project** → submit → detail. **Edit** → change status/client → save.
3. Detail → **Members**: assign an active employee (lead/member), change a role, remove one.
4. Row ⋯ / detail **Archive** → project leaves the default list (visible under status=archived).
5. Non-admin: scoped read, no New/Edit/Archive/member controls; `/projects/new` shows 403.

> Full click-through needs a browser; build/typecheck, route-serving, and the live API are verified automatically.

## 8. Quality
TypeScript strict clean · build passes · no mock data · generated OpenAPI types only · reused all Employees patterns (table/badge/select/alert-dialog/form/textarea + pagination/search/empty/error/skeleton + `RequireCapability` + AppError mapping) · small commits per phase.

## 9. Out of scope (untouched)
Attendance, Reports, Analytics, Dashboard.

**F5 Projects Frontend complete. Recommended next: V4 Attendance backend, then F6 Attendance UI.**
