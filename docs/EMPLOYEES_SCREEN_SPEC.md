# Employees Screen Spec

> Routes `/employees` (list) and `/employees/[id]` (detail/edit) · admin (CRUD), manager (team read), employee (self), viewer (read). No-code UX spec. NB: the employees API is a **next backend phase**; this spec defines the contract the frontend expects.

## Purpose
Directory of people with role/department/manager, plus per-employee detail. Admin manages records; managers view their team; everyone can see their own profile.

## Layout
**List:** PageHeader (title + count + [Invite/Add] for admin) → Toolbar (search + filter chips + view) → DataTable (paginated). **Detail:** back link → header (avatar, name, status) → tabbed sections (Profile · Reporting line · Attendance summary · Reports) with Edit (admin/self-profile).

## Desktop wireframe — list
```
┌────────────┬─────────────────────────────────────────────────────────────────────┐
│ ▸ Employees│ Workspace / Employees                     ⌘K Search   🔔  ?   (PR) ▾ │
│            ├─────────────────────────────────────────────────────────────────────┤
│            │  Employees · 47                                   [ ⌂ Filter ] [+ Add]│
│            │  ┌───────────────────────────────────────────────────────────────┐  │
│            │  │ 🔍 Search name or code…   [Dept: Platform ×][Status: active ×] │  │
│            │  ├──────┬───────────────┬──────────┬──────────┬─────────┬─────────┤  │
│            │  │      │ Member        │ Role     │ Dept     │ Manager │ Status  │  │
│            │  ├──────┼───────────────┼──────────┼──────────┼─────────┼─────────┤  │
│            │  │ (PR) │ Priya R.      │ Sr Eng   │ Platform │ Marco V │ ●active │  │
│            │  │ (JK) │ Jordan Kim    │ Engineer │ Mobile   │ Marco V │ ●active │  │
│            │  │ (RS) │ Riya Shah     │ Engineer │ Web      │ Marco V │ ●leave  │  │
│            │  │ …                                                              … │  │
│            │  ├───────────────────────────────────────────────────────────────┤  │
│            │  │ Showing 1–20 of 47            [ ‹ Prev ]  [ Next › ]           │  │
│            │  └───────────────────────────────────────────────────────────────┘  │
└────────────┴─────────────────────────────────────────────────────────────────────┘
```

## Desktop wireframe — detail
```
← Employees
┌───────────────────────────────────────────────────────────────────────┐
│ (PR)  Priya Ramanujan   ●active            [ Edit ] (admin/self)        │
│ EMP-00184 · Senior Engineer · Platform · Manager: Marco Velez           │
├──────────────[ Profile ][ Reporting line ][ Attendance ][ Reports ]─────┤
│ Profile                                                                 │
│  Work email   priya@…            Phone     +91 …                         │
│  Department   Platform           Designation Senior Engineer            │
│  Manager      Marco Velez        Joined    2024-03-12                    │
│  Status       active             User       linked (admin)              │
└───────────────────────────────────────────────────────────────────────┘
```

## Mobile wireframe — list
```
┌─────────────────────────────┐
│ ☰  Employees       🔔 (PR)▾ │
│ 47 people          [+ Add]  │
│ 🔍 Search…        [Filter ▾]│
│ ┌─────────────────────────┐ │
│ │(PR) Priya R.    ●active │ │
│ │ Sr Eng · Platform       │ │
│ ├─────────────────────────┤ │
│ │(JK) Jordan Kim  ●active │ │
│ │ Engineer · Mobile       │ │
│ └─────────────────────────┘ │
│ Showing 1–20 of 47  [Next ›]│
└─────────────────────────────┘
```

## Components
PageHeader, SearchInput, FilterBar/FilterChip, DataTable, Avatar, Badge, Pagination, Tabs (detail), Field (edit form in Modal or detail-edit), Button, Modal (Add/Invite), EmptyState/ErrorState/Skeleton.

## Tables
Columns: Avatar+Name · Role · Department · Manager · Status (+ row overflow `⋯` for admin: Edit, Deactivate). Sort by name/department/status (client or server). Row → `/employees/[id]`. Selectable checkboxes only if bulk actions added later (not v1).

## Filters
Department (select), Status (active/on_leave/exited), Manager (select). Applied as removable chips; reflected in URL (`?dept=&status=&manager=`). "Clear all".

## Search
Debounced name/employee-code search (`?q=`); server-side `ILIKE`. Empty query shows all (paginated).

## Pagination
Offset-based, 20/page; "Showing X–Y of N" + Prev/Next. Page in URL (`?offset=`). Preserves filters/search.

## Empty states
- No employees at all (fresh tenant) → EmptyState "No employees yet" + [Add employee] (admin) / passive text (others).
- Search/filter no match → "No employees match these filters" + [Clear all].
- Manager with no reports → "You have no direct reports yet."

## Loading states
Table → 8–10 skeleton rows (avatar + 2 text lines); detail → header skeleton + tab skeleton. Filters/search remain interactive (disabled submit while loading).

## Error states
- List fetch fail → ErrorState with Retry replacing table body; toolbar stays.
- Detail 404 → in-shell NotFound "Employee not found."
- Edit save 422 → inline field errors; 409 (e.g., duplicate code) → field error; 403 → toast "You don't have permission."

## Mobile responsiveness
Table → stacked cards (avatar, name, status badge, role·dept line; tap → detail). Filters → bottom sheet / dropdown. Detail tabs → horizontally scrollable tab bar; fields single-column.

## RBAC behavior
- **admin:** full list, Add/Edit/Deactivate, see all departments; reassign manager; cannot deactivate self.
- **manager:** sees **own team** (employees where `manager_id = self`); read-only; opens member detail; no Add/Edit.
- **employee:** list hidden from nav; can reach **own** `/employees/[self]` (profile) via avatar menu; edits limited profile fields (if FD-3 self-edit allowed) else read-only.
- **viewer:** read-only directory; no actions.
Actions are both nav-hidden and API-enforced; the `[+ Add]`/`[Edit]`/overflow actions render only when `can(role,'employee.manage')`.

_API (expected next phase, per `openapi-v1.yaml`): `GET /employees?q&status&manager_id&limit&offset`, `POST /employees`, `GET/PATCH /employees/{id}`, `GET /employees/{id}/team`._
