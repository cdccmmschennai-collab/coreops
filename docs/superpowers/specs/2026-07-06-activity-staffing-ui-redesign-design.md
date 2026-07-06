# Activity Staffing UI Redesign — Design Spec

**Status:** Approved (refined 2026-07-06)
**Date:** 2026-07-06
**Scope:** Frontend redesign of the project Activity Staffing surface + one targeted backend endpoint to fix the employee dropdown. No changes to existing business logic, permissions, DB, or existing endpoints.

---

## 1. Problem

The Head-only **"Activities" card** (`ProjectHeadActivities` in `project-head.tsx`) renders **one card per activity**, each with its own Add-member form (Employee / Role / QC / Add). Projects with many activities show 20+ duplicated dropdowns.

Separately, the Employee dropdown shows **only one employee** for a Head — root cause `employees/service.py:89-90`: a Head's global role is `employee`, so `GET /employees` returns only their own record.

---

## 2. Goals

1. One **shared assignment form** at the bottom of the Members card; remove the per-activity forms.
2. Members card shows **Project Head first**, then **only activities that have ≥1 assignment** (no empty "No one assigned" sections), ordered by the activity master **`sort_order`** (benchmark order), not alphabetically.
3. Fix the Employee dropdown to list **all active employees**, via a minimal new backend endpoint scoped to staffing managers.
4. **Activity dropdown** in the form lists **only benchmark / project-execution activities** — excludes attendance/system activities (Leave, Company Holiday, Week Off, Work From Home, Work At Office, Comp-Off, Overtime, Permission).
5. **Visibility:** everyone (PM, Head, Lead, Contributor, any member) sees the staffing view; **only authorized users** (PM or the project Head) can modify (form + remove).
6. No redesign of cards, typography, or spacing.

---

## 3. Backend change (minimal, additive)

### New endpoint

`GET /projects/{project_id}/assignable-employees` → `list[EmployeeOut]`

- **Authorization:** reuse `authz.can_manage_activity_staffing(db, actor, project)` — the exact check the assign/remove endpoints already use (PM for any project, or the project's Head). No new permission concept.
- **Returns:** all **active, non-deleted** employees, ordered by name (the same rows a PM already sees from `/employees?status=active`).

### Service (`projects/service.py`)

```python
def list_assignable_employees(db, actor, project_id) -> list[Employee]:
    project = _fetch(db, project_id)
    if not authz.can_manage_activity_staffing(db, actor, project):
        raise AppError("forbidden", "Only the PM or the project Head can view assignable employees.", 403)
    return db.execute(
        select(Employee)
        .where(Employee.deleted_at.is_(None), Employee.status == EmployeeStatus.active)
        .order_by(Employee.first_name, Employee.last_name)
    ).scalars().all()
```

`Employee` and `EmployeeStatus` are already imported. Serialized with the existing `EmployeeOut` schema (already exposes `id`, `full_name`, `employee_code`). No new schema, no DB change, no change to `/employees` scoping.

**Rationale for a new endpoint over widening `/employees`:** widening `list_employees` would expose the full directory to every employee-role user app-wide. A project-scoped endpoint guarded by the existing staffing permission is surgical.

### Router (`projects/router.py`)

New route mirroring `GET /{project_id}/activity-staffing`, `response_model=list[EmployeeOut]` (import `EmployeeOut` from `app.modules.employees.schemas`), delegating to the service function.

---

## 4. Frontend changes

### 4.1 New API wiring (`features/projects`)

- `types.ts`: `AssignableEmployee = { id: string; full_name: string; employee_code: string }`.
- `api.ts`: `listAssignableEmployees(id)` → `GET /projects/{id}/assignable-employees`.
- `keys.ts`: `assignableEmployees(id)`.
- `hooks.ts`: `useAssignableEmployees(id, enabled)` — `enabled` gates the fetch to authorized viewers.

### 4.2 Members card (`project-members.tsx`)

The read view already matches the target (Head pinned, one section per **assigned** activity in `sort_order` from `useActivityStaffing`, read-only rows). Changes:

- Compute `canModifyStaffing = isPM || isHead` (`isHead = useAuth().employeeId === project.head_employee_id`; `isPM = can(role, "project.manage")`).
- For authorized viewers on a non-archived project, add an **unobtrusive remove (×)** per assignment row (`useRemoveActivityMember`) — preserves the current unassign ability without a per-activity form.
- Keep the existing PM-only "Assign/Change Head" form unchanged.
- Render the new **shared assignment form** below the sections, only when `canModifyStaffing && !archived`.

### 4.3 Shared assignment form

Existing primitives (Select, Checkbox, Button), current spacing:

- **Employee** ▼ — `useAssignableEmployees(project.id, canModifyStaffing)` (all active employees).
- **Activity** ▼ — `useActivities(true)`, `level === 'activity'`, **filtered to benchmark/project-execution activities** (see 4.4).
- **Role** ▼ — Lead / Contributor. Lead option disabled when the selected activity already has a Lead (from the staffing map) — mirrors today's guard, avoids the backend one-Lead 409.
- **☐ QC** — optional.
- **Add Assignment** — `useAssignActivityMember({ activityId, body: { employee_id, role, is_qc } })`. On success: toast, reset fields; existing invalidation refreshes the sections. Disabled until Employee + Activity chosen.

### 4.4 Benchmark activity filter

Exclude attendance/system activities by name (case-insensitive), matching the backend's canonical set in `scripts/deactivate_attendance_activities.py`:

```
LEAVE, COMPANY HOLIDAY, WORK FROM HOME, WEEK OFF, WORK AT OFFICE,
COMP-OFF, OVERTIME HOURS-COMPENSATION, OVERTIME HOURS-SALARY, PERMISSION
```

Predicate: keep an activity unless its upper-cased name is in the exclusion set or starts with `OVERTIME`. This is a frontend safeguard on top of the intended `is_active=false` mechanism (these rows are meant to be deactivated); it needs no data or backend change.

### 4.5 Remove the old card

- `project-detail.tsx`: remove the `ProjectHeadActivities` import and usage.
- Delete `project-head.tsx` (no other importers).

---

## 5. Verification

1. Authorized user assigns Lead/Contributor/QC via the single shared form → row appears in the correct section.
2. Employee dropdown lists all active employees (as a Head).
3. Activity dropdown excludes attendance/system activities.
4. Only assigned activities render, Head first, in `sort_order`.
5. Remove (×) still unassigns.
6. Everyone can view; only PM/Head see the form + ×.
7. `npm run build` and `npm run typecheck` pass; backend endpoint returns active employees for PM/Head, 403 otherwise.

---

## 6. Out of scope / untouched

`/employees` scoping, existing activity-staffing endpoints, permissions, DB/migrations, the Activities tab (`ActivitiesTab`), Submissions tab, and all typography/spacing/card chrome.
