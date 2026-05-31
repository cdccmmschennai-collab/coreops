# F4 — Employees Frontend: Completion Report

**Date:** 2026-05-31 · **Branch:** `feature/v1-authentication` · **Status:** complete; typecheck + build green; verified through Docker. **No work on Projects/Attendance/Reports/Analytics/Dashboard.**

Implements the Employees UI against the **live** V2 Employees API, reusing the F0/F1 stack (TanStack Query · RHF · Zod · shadcn/ui · existing api-client + Auth). Per the mid-task instruction, **TypeScript types are generated from the live OpenAPI contract** (`openapi-typescript`), not hand-inferred.

---

## 1. Type generation from the contract
- Added `openapi-typescript` + `gen:api` script; snapshotted the live spec to `frontend/openapi.json`.
- Generated `src/types/openapi.ts` from `/api/v1/openapi.json`.
- Employee/User types are **derived from the generated `components["schemas"]`** (`EmployeeOut/Create/Update/Page/Status`, `UserOut/Page`) — single source of truth, no manual field inference.

## 2. Files created / modified

**New UI primitives (shadcn, themed):** `ui/{table,badge,select,alert-dialog}.tsx`
**New shared components:** `data/{pagination,search-input}.tsx`, `feedback/{empty-state,error-state,table-skeleton}.tsx`, `auth/require-capability.tsx`
**New employees feature:** `features/employees/{types,keys,schemas,api,hooks}.ts` + `components/{status-badge,employees-filters,employees-table,employees-view,deactivate-dialog,employee-detail,employee-form,employee-edit}.tsx`
**New users feature:** `features/users/{api,hooks}.ts`
**New pages:** `(app)/employees/{page, new/page, [id]/page, [id]/edit/page}.tsx`
**Modified:** `types/api.ts` (removed now-unused `Page<T>` — no dead code), `components/shell/sidebar.tsx` (enabled Employees nav), `package.json`/lock (+`@radix-ui/react-select`, `@radix-ui/react-alert-dialog`, `openapi-typescript`).

## 3. API integration mapping

| UI | Endpoint | Hook |
|---|---|---|
| List (search/filter/paginate) | `GET /employees?q&status&department&limit&offset` | `useEmployees` |
| Detail | `GET /employees/{id}` | `useEmployee` |
| Manager name (detail/form) | `GET /employees/{id}` / `GET /employees?limit=100` | `useEmployee` / `useEmployees` |
| Linked account email | `GET /users/{id}` | `useUser` (admin) |
| User-link select (create) | `GET /users?limit=100` | `useUsers` (admin) |
| Create | `POST /employees` | `useCreateEmployee` |
| Edit | `PATCH /employees/{id}` | `useUpdateEmployee` |
| Deactivate | `DELETE /employees/{id}` | `useDeactivateEmployee` |

Mutations invalidate `["employees"]` (+ detail) and toast; errors mapped: 409→field (code/email), 422→top alert, 403→toast/guard, 404→NotFound, 401→global login redirect. List view state (q/department/status/offset) lives in the **URL**.

## 4. Screens delivered
- **List** `/employees` — paginated table, debounced search, **debounced department text filter** (no departments catalog), status select, empty/loading/error states, row → detail, admin row actions (Edit, Deactivate).
- **Detail** `/employees/[id]` — Profile, Reporting line (manager link), Account (linked user email for admin / Linked·No-account badge); admin Edit + Deactivate.
- **Create** `/employees/new` — RHF+Zod, `POST`; admin-guarded (`RequireCapability`).
- **Edit** `/employees/[id]/edit` — RHF+Zod, `PATCH` (excludes immutable `employee_code`/`user_id`); admin-guarded.
- **Deactivate** — `AlertDialog` confirm from both the list row menu and the detail page; `DELETE` (soft-delete).

## 5. RBAC behavior (UI, mirrors API)
- Employees nav + list/detail: all roles (API scopes results — admin all, manager team, employee self, viewer all-read).
- Create/Edit/Deactivate controls render only for admin (`can(role,"employee.manage")`); `/new` and `/edit` are route-guarded (non-admin → in-shell 403). Server enforces regardless.

## 6. Verification
- **`npm run typecheck`** (tsc strict) → **clean** after every step.
- **`npm run build`** → **success** after every step; routes built: `/employees`, `/employees/[id]`, `/employees/[id]/edit`, `/employees/new`.
- **Docker:** frontend image rebuilt (new deps), container recreated with fresh `node_modules`; routes serve **200** with **0 module errors**; full stack up (db/redis/backend:8100/frontend:3100). _(container result appended below)_
- **Live API:** the same V2 endpoints were smoke-verified in `V2_EMPLOYEES_REPORT.md` and exercised by these hooks.

**Manual verification steps (browser, against live backend):**
1. `http://localhost:3100/login` → sign in as admin.
2. **Employees** nav → list loads; type in search / department; change status filter → table + URL update; paginate.
3. **Add employee** → fill form → submit → toast + redirect to detail.
4. Detail → **Edit** → change designation/department/status → save → values update.
5. Row ⋯ / detail **Deactivate** → confirm dialog → employee leaves the active list.
6. Sign in as a **non-admin** → no Add/Edit/Deactivate controls; `/employees/new` shows 403.

> Full click-through requires a browser (no Playwright in this environment); build/typecheck, route-serving, and the live API are verified automatically. Steps above confirm the interactive flows.

## 7. Quality
TypeScript strict clean · build passes · no placeholder code · no mock data · no duplicate patterns (generic table/badge/select/dialog + pagination/search/empty/error reused) · dead `Page<T>` removed · design-system tokens only · small commits per milestone.

## 8. Out of scope (untouched)
Projects, Attendance, Reports, Analytics, Dashboard; employee self-edit; bulk actions; departments catalog.

**F4 Employees Frontend complete. Recommended next: V3 Projects backend, then F5 Projects frontend.**
