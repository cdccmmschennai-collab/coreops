# F4 — Employees Frontend: Implementation Plan

> **Phase:** Plan only (no code until reviewed). Builds the Employees UI against the **live** V2 Employees API (`localhost:8100/api/v1/employees`). Reuses the F0/F1 stack: TanStack Query · RHF · Zod · shadcn/ui · existing `api-client` + Auth.

---

## 1. Architecture review (current state)

**What exists and will be reused as-is:**
- **API client** `src/lib/api-client.ts` — `api.get/post/patch/del`, JWT attach, error envelope → `AppError`. ✅ no changes.
- **Query client** `src/lib/query-client.ts` — global 401 → `/login`, retry policy. ✅ reuse.
- **Auth** `features/auth/auth-provider.tsx` — `useAuth() → {status, user, role}`. ✅ reuse for RBAC gating.
- **RBAC** `src/lib/rbac.ts` — `can(role, "employee.manage")` already maps to `["admin"]`. ✅ reuse (no new capability needed).
- **Types** `src/types/api.ts` — `Role`, `User`, `Page<T>`. → **extend** with `Employee`, `EmployeeStatus`.
- **Shell** `components/shell/*` (AppShell/Sidebar/TopNav/PageHeader). Sidebar currently renders **Employees as `soon` (disabled)** → **enable it**.
- **UI primitives present:** button, input, label, card, form, avatar, dropdown-menu, separator, skeleton, sonner.

**Gaps to fill (new shadcn primitives + data/feedback components):**
- **Missing UI primitives:** `table`, `badge`, `select` (Radix), `alert-dialog` (Radix) for the destructive confirm.
- **Missing data components:** `Pagination`, `SearchInput` (debounced).
- **Missing feedback components:** `EmptyState`, `ErrorState`, `TableSkeleton`.
- **New deps:** `@radix-ui/react-select`, `@radix-ui/react-alert-dialog` (added to `package.json`; both are standard shadcn deps).

**Routing:** follows the existing `(app)` group + the `/reports/new` & `/reports/[id]` precedent → add `employees`, `employees/new`, `employees/[id]`, `employees/[id]/edit`.

**State model (per `FRONTEND_ARCHITECTURE.md`):** server state via **TanStack Query**; list view state (search/filters/pagination) in the **URL** (`?q=&department=&status=&limit=&offset=`) → deep-linkable, back-button correct. Forms via **RHF + Zod**; backend `AppError` (409/422) mapped to field/top errors (reusing the `login-form` pattern).

**RBAC behavior (matches V2 API + matrix):**
- Employees **nav + list/detail**: visible to all authenticated roles (API scopes results: admin=all, manager=team, employee=self, viewer=all-read).
- **Create / Edit / Deactivate**: admin only — gated by `can(role,"employee.manage")` (button hidden) **and** route-guarded (non-admin hitting `/new` or `/edit` → in-shell 403). Server enforces regardless.

---

## 2. Files to create / modify

### Create — UI primitives (shadcn)
- `src/components/ui/table.tsx`
- `src/components/ui/badge.tsx`
- `src/components/ui/select.tsx`
- `src/components/ui/alert-dialog.tsx`

### Create — shared data/feedback components
- `src/components/data/pagination.tsx` — "Showing X–Y of N" + Prev/Next (offset-based)
- `src/components/data/search-input.tsx` — debounced text input
- `src/components/feedback/empty-state.tsx`
- `src/components/feedback/error-state.tsx` — message + Retry
- `src/components/feedback/table-skeleton.tsx`
- `src/components/auth/require-capability.tsx` — client guard (renders 403 ErrorState if `!can(role, cap)`)

### Create — employees feature
- `src/features/employees/keys.ts` — query-key factory (`employeesKeys.list(params)`, `.detail(id)`)
- `src/features/employees/schemas.ts` — Zod `employeeCreateSchema`, `employeeUpdateSchema`, status enum; inferred input types
- `src/features/employees/api.ts` — `employeesApi.{list,get,create,update,deactivate}`
- `src/features/employees/hooks.ts` — `useEmployees`, `useEmployee`, `useCreateEmployee`, `useUpdateEmployee`, `useDeactivateEmployee`
- `src/features/employees/components/employee-form.tsx` — shared Create/Edit form (RHF + Zod)
- `src/features/employees/components/employees-table.tsx`
- `src/features/employees/components/employees-filters.tsx` — search + department + status
- `src/features/employees/components/status-badge.tsx`
- `src/features/employees/components/deactivate-dialog.tsx`

### Create — users feature (small, for the manager/user-link selects on the form + detail)
- `src/features/users/api.ts` + `src/features/users/hooks.ts` — `useUsers()` (list, admin) and `useUser(id)` (linked-account email on detail). Reuses live `/users` endpoints.

### Create — pages
- `src/app/(app)/employees/page.tsx` — list
- `src/app/(app)/employees/new/page.tsx` — create (admin-guarded)
- `src/app/(app)/employees/[id]/page.tsx` — detail
- `src/app/(app)/employees/[id]/edit/page.tsx` — edit (admin-guarded)

### Modify
- `src/types/api.ts` — add `EmployeeStatus`, `Employee` (response type) [+ reuse `Page<T>`]
- `src/components/shell/sidebar.tsx` — enable Employees nav (remove `soon`)
- `frontend/package.json` — add the 2 Radix deps

> No duplication: the table/badge/select/dialog primitives and EmptyState/ErrorState/Pagination/SearchInput are **generic** and will be reused by Projects/Attendance/Reports later. The employee-specific bits live under `features/employees/`.

---

## 3. API integration mapping

| UI action | Endpoint | Hook | Query key / invalidation |
|---|---|---|---|
| List (search/filter/paginate) | `GET /employees?q&status&department&manager_id&limit&offset` | `useEmployees(params)` | key `employeesKeys.list(params)` |
| Detail | `GET /employees/{id}` | `useEmployee(id)` | `employeesKeys.detail(id)` |
| Manager info (detail) | `GET /employees/{managerId}` | `useEmployee(managerId, {enabled})` | `employeesKeys.detail(managerId)` |
| Linked user (detail, admin) | `GET /users/{userId}` | `useUser(userId, {enabled: admin})` | `usersKeys.detail(userId)` |
| Manager/user selects (form) | `GET /employees?limit=100`, `GET /users?limit=100` | `useEmployees`, `useUsers` | respective list keys |
| Create | `POST /employees` | `useCreateEmployee()` | onSuccess → invalidate list; toast; route → detail |
| Edit | `PATCH /employees/{id}` | `useUpdateEmployee(id)` | invalidate detail + list; toast; route → detail |
| Deactivate | `DELETE /employees/{id}` | `useDeactivateEmployee()` | invalidate list (+detail); toast; route → list |

**Error mapping (AppError → UI):** `409` (duplicate code/email / user already linked) → field error on `employee_code`/`work_email` (or top alert); `422` (invalid/self manager, validation) → top alert + field message; `403` → toast "You don't have permission"; `404` (detail) → in-shell NotFound; `401` → handled globally (login redirect).

**Department filter:** backend `department` is free-text (no catalog endpoint) → the filter is a **debounced text input** mapping to `?department=` (ILIKE). (Documented deviation from the "select" wireframe — honest given no departments table.) **Status filter:** Select of `active | on_leave | exited`.

---

## 4. Component hierarchy

```
/employees (list page)
└─ PageHeader (title + [Add employee] · admin)
   ├─ EmployeesFilters (SearchInput · DepartmentInput · StatusSelect)   ← writes URL params
   └─ EmployeesTable (useEmployees)
      ├─ Table (ui) rows → row click → /employees/[id]
      │   └─ StatusBadge, Avatar, row ⋯ (admin: Edit, Deactivate→DeactivateDialog)
      ├─ TableSkeleton (loading) | EmptyState (no data) | ErrorState (error)
      └─ Pagination (total/limit/offset → URL)

/employees/new (create page)  ─ RequireCapability("employee.manage")
└─ PageHeader → EmployeeForm(mode="create", useCreateEmployee)

/employees/[id] (detail page)
└─ PageHeader (Edit · Deactivate — admin)
   ├─ Card: Profile (code, name, email, phone, department, designation, join date, StatusBadge)
   ├─ Card: Reporting line (manager via useEmployee(manager_id))
   └─ Card: Account (linked user via useUser — admin; else Linked/Not linked badge)

/employees/[id]/edit (edit page)  ─ RequireCapability("employee.manage")
└─ PageHeader → EmployeeForm(mode="edit", useEmployee + useUpdateEmployee)

EmployeeForm (shared)
└─ Form (RHF+Zod): employee_code*, first_name*, last_name*, work_email, phone,
                   department, designation, date_of_joining, status,
                   manager_id (Select←employees), user_id (Select←users · create/admin)
   └─ submit → create/update mutation; field/top error mapping
```

---

## 5. Implementation plan (ordered, with checkpoints)

Each step ends with **`npm run typecheck` + `npm run build`** (both must pass) and a small commit. The Docker `frontend` container will be rebuilt once (new deps) at the end for stack parity.

1. **Deps + primitives** — add `@radix-ui/react-select`, `@radix-ui/react-alert-dialog`; create `ui/table`, `ui/badge`, `ui/select`, `ui/alert-dialog`. _Commit:_ `feat(ui): table, badge, select, alert-dialog primitives`.
2. **Shared data/feedback** — `data/pagination`, `data/search-input`, `feedback/{empty-state,error-state,table-skeleton}`, `auth/require-capability`. _Commit:_ `feat(ui): data + feedback components`.
3. **Employees data layer** — `types/api.ts` (Employee types), `features/employees/{keys,schemas,api,hooks}`, `features/users/{api,hooks}`. _Commit:_ `feat(employees): data layer (types, api, hooks, schemas)`.
4. **List page** — `employees-table`, `employees-filters`, `status-badge`, `employees/page.tsx`; enable sidebar nav. _Commit:_ `feat(employees): list page (table, search, filters, pagination, states)`.
5. **Detail page** — `employees/[id]/page.tsx` (profile + manager + linked account). _Commit:_ `feat(employees): detail page`.
6. **Create + Edit** — `employee-form`, `employees/new`, `employees/[id]/edit` (admin-guarded). _Commit:_ `feat(employees): create + edit forms (RHF/Zod)`.
7. **Deactivate** — `deactivate-dialog` wired into table row + detail. _Commit:_ `feat(employees): deactivate with confirm dialog`.
8. **Verify** — full `typecheck` + `build`; rebuild Docker frontend; manual smoke (admin: list/search/filter/create/edit/deactivate; non-admin: scoped read, no write controls). _Commit:_ `docs: F4 report` (`docs/FRONTEND_F4_EMPLOYEES_REPORT.md`).

**Quality gates:** TypeScript strict clean, build passes, no dead/placeholder code, no duplicate patterns (generic primitives shared), design-system tokens only.

**Out of scope (not touched):** Projects, Attendance, Reports; employee self-edit; bulk actions; departments catalog.

---

### Open questions for review
- **Q1 — Manager/User selects:** OK to add a tiny `features/users` (`useUsers`) so the form's *user-account link* and the detail's *linked email* work against the live `/users` API? (Alternative: omit user-link from the create form for now.)
- **Q2 — Department filter as text input** (no departments catalog) instead of a Select — acceptable?
- **Q3 — Routes** `/employees/new` and `/employees/[id]/edit` (separate pages, matching the `/reports/new` precedent) vs. modal forms — confirm pages.

Awaiting approval to start at Step 1.
