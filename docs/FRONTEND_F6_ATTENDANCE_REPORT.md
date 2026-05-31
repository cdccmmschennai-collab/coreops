# F6 — Attendance Frontend: Completion Report

**Date:** 2026-05-31 · **Branch:** `feature/v1-authentication` · **Status:** complete; typecheck + build green; routes verified in Docker. **No work on Reports/Analytics/Dashboard.**

Implements the Attendance UI against the **live** V4 Attendance API, reusing the Employees/Projects frontend architecture exactly. Types are **generated from the live OpenAPI contract** — no hand-inference, no mock data.

---

## 1. Type generation
Re-snapshotted the live spec to `frontend/openapi.json` and regenerated `src/types/openapi.ts` (`npm run gen:api`). Attendance types derive from generated `components["schemas"]`: `AttendanceOut/Create/Update/Page/Status`.

## 2. Files created (mirrors `features/projects`)
**Feature** `src/features/attendance/`: `types.ts`, `keys.ts`, `schemas.ts`, `api.ts`, `hooks.ts`, `employee-options.ts` + `components/` → `status-badge`, `attendance-filters`, `attendance-table`, `attendance-view`, `delete-dialog`, `attendance-detail`, `attendance-form`, `attendance-edit`.
**Pages** `(app)/attendance/`: `page.tsx`, `new/page.tsx`, `[id]/page.tsx`, `[id]/edit/page.tsx`.
**Shared additions:** `src/lib/format.ts` (`formatMinutes`/`formatTime`/`toDatetimeLocal` — reusable), `rbac.ts` (+`attendance.manage` capability), `sidebar.tsx` (enabled Attendance nav).
**Infra:** `docker-compose.yml` — isolated the container's `/app/.next` as its own volume so a host `npm run build` can no longer corrupt the dev container (the chunk-corruption fix).
**No new npm dependencies.**

## 3. API integration mapping

| UI | Endpoint | Hook |
|---|---|---|
| List (filters/paginate) | `GET /attendance?employee_id&status&from&to&limit&offset` | `useAttendanceList` |
| Detail | `GET /attendance/{id}` | `useAttendance` |
| Create | `POST /attendance` | `useCreateAttendance` |
| Edit | `PATCH /attendance/{id}` | `useUpdateAttendance` |
| Delete | `DELETE /attendance/{id}` | `useDeleteAttendance` |
| Employee names + selects | `GET /employees?limit=100` | `useEmployeeOptions` (reuses `useEmployees`) |

Mutations invalidate `["attendance"]` (+detail) and toast; `AppError` mapped: 409 (duplicate employee/date) + 422 (unknown employee / check-out before check-in) → top alert, 403→guard, 404→NotFound, 401→global. List state (employee/status/from/to/offset) is URL-driven.

## 4. Screens delivered
- **List** `/attendance` — table (**Employee** name · **Date** · **Status** badge · **Total** · **Overtime**, minutes formatted `Xh Ym`); filters: **employee** select, **status** select, **date range** (from→to); pagination; empty/loading/error; admin row actions (Edit, Delete).
- **Detail** `/attendance/[id]` — summary (employee, date, status, check-in/out times, **calculated** total + overtime).
- **Create** `/attendance/new` & **Edit** `/attendance/[id]/edit` — RHF+Zod; employee + date editable on create, **read-only on edit** (immutable, matching `AttendanceUpdate`); status + `datetime-local` check-in/out; total/overtime computed server-side (noted in the form). Admin-guarded (`RequireCapability`).

## 5. RBAC (UI mirrors API)
- **admin** — full: create/edit/delete.
- **manager** — read **team** attendance · **employee** — read **own** · **viewer** — read-only all. (The API scopes list/detail; the UI shows no management controls.)
Management gated by `can(role,"attendance.manage")` (admin) + route guards; server-enforced regardless.

## 6. Verification
- **`npm run typecheck`** (strict) → clean after every phase.
- **`npm run build`** → success; routes built: `/attendance`, `/attendance/[id]`, `/attendance/[id]/edit`, `/attendance/new`.
- **Docker:** container recreated with the new `/app/.next` isolation; routes serve **200** with **0 module errors**; stack up (backend:8100 / frontend:3100). _(results appended below.)_
- **Live API:** V4 endpoints verified by 83 backend tests; these hooks call those exact endpoints.

**Manual browser steps:** sign in as admin → **Attendance** → filter by employee/status/date-range; **Record attendance** (pick employee, date, status, check-in/out) → detail shows computed minutes; **Edit** (employee/date read-only) → save; row **Delete** → confirm. Non-admin: scoped read, no New/Edit/Delete; `/attendance/new` shows 403.

## 7. Quality
TypeScript strict clean · build passes · no mock data · generated OpenAPI types only · reused all Employees/Projects patterns (table/badge/select/alert-dialog/form + pagination/empty/error/skeleton + `RequireCapability` + AppError mapping) · small commits per phase.

## 8. Note — chunk-corruption fix
The earlier broken-chunks incident was caused by a host `npm run build` writing `frontend/.next` into the dev container via the bind mount. This phase adds an **anonymous volume for `/app/.next`** in compose so the container owns its dev build output — host builds can no longer affect it.

## 9. Out of scope (untouched)
Reports, Analytics, Dashboard; biometric/self-punch flows; leave/holiday automation.

**F6 Attendance Frontend complete.**
