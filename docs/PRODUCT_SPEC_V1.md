# CoreOps — Product Specification (v1)

**Status:** Draft for approval · **Date:** 2026-06-01 · **Owner:** Product
**Scope:** Single-tenant Workforce Management System (WMS), co-hosted with SPIR.
**Codename:** CoreOps (brand-agnostic; product name = `PRODUCT_NAME` / `--product-name`).

This is the single source of truth for the locked v1 business decisions. It supersedes the
ad-hoc notes in `REMAINING_ROADMAP.md` for the modules below. The detailed module spec for the
new priority module lives in **[DAILY_WORK_REPORTS_SPEC.md](./DAILY_WORK_REPORTS_SPEC.md)**.

---

## 1. Product pillars

The WMS is built around five domains:

1. **Employees** — workforce directory, org structure (department, designation, manager), lifecycle.
2. **Projects** — project records + membership/assignments.
3. **Attendance** — daily attendance with derived worked/overtime minutes.
4. **Daily Work Reports (DWR)** — employees log daily work against projects; reviewed by managers. *(NEW priority module.)*
5. **RBAC** — four fixed roles: `admin`, `manager`, `employee`, `viewer`.

Supporting surfaces: **Dashboard**, **Reports** (export), **Analytics** (deferred), **Settings**.

### 1.1 Current build state (factual)

| Module | Backend | Frontend |
|---|---|---|
| Auth / RBAC | ✅ live | ✅ live |
| Employees | ✅ live | ✅ live |
| Projects | ✅ live | ✅ live |
| Attendance | ✅ live | ✅ live |
| Settings → Users & Roles | ✅ live (`/users`) | 🟡 list only (Phases 4–5 pending) |
| Dashboard | ❌ none | 🟡 static placeholder |
| Reports | ❌ none | ❌ none (nav "soon") |
| Analytics | ❌ none | ❌ none (nav "soon") |
| **Daily Work Reports** | ❌ none | ❌ none |

### 1.2 Locked sequencing

**Daily Work Reports (backend → frontend) → finish Settings (Phases 4–5) → Dashboard → Reports → Analytics (deferred).**

DWR is promoted to the next module because Dashboard and Reports both depend on its data
(employee "submitted reports" metric; future hours-by-project reporting).

---

## 2. Locked business decisions

### 2.1 Dashboard — role-specific

Three role-tailored dashboards. Period default **This month** with a Today/Week toggle where sensible.
No "recent activity" feed in v1 (no audit log exists yet).

- **Admin** — total employees · present today · absent today · on leave (today) · active projects · attendance percentage (today).
- **Manager** — team-focused versions of the above, scoped to the manager's team (present/absent/on-leave today for the team, team attendance %, team's active projects, **pending work-report reviews**).
- **Employee** — personal: my attendance (this month summary) · my assigned projects · my submitted work reports (this week: draft/submitted/approved counts).

> Dashboard is **not implemented in this pass** — spec only. It will be built after DWR + Settings.
> Dashboard KPIs require new read/aggregation endpoints (computed **live** per request in v1; single-tenant data volumes are small).

### 2.2 Attendance — policy + enhancements

- **Standard workday = 480 minutes** (8h).
- **Overtime starts after 480 minutes** worked in a day (`overtime_minutes = max(0, worked − 480)`).
- **Half-day = 240 minutes** (derived convention).
- **Management restricted to `admin` and `manager`.** *(Change from current `attendance.manage` = admin-only.)*
  Manager may manage attendance for their team only; employees and viewers are read-only.
- **Leave remains a status only** — no request/approval workflow in v1.
- **Future: calendar view** — a month grid per employee with color-coded daily statuses
  (present/absent/half-day/leave/holiday/weekend). Spec'd as a later enhancement, not this pass.

> **RBAC change implied:** today `attendance.manage = [admin]`. To honour "admin and manager",
> introduce manager-scoped management. This is a deliberate change — see §3.

### 2.3 Reports (export module)

Canned, parameterised reports. **Export formats: CSV and XLSX only.** Synchronous generation in v1
(on-demand, no stored artifacts). Manager-run reports are scoped to their team/projects; admin org-wide.

v1 report catalogue:
1. **Attendance Summary** — per employee, per period: days present/absent/leave/half-day, total + overtime minutes.
2. **Daily Attendance Register** — one row per employee per day for a date range.
3. **Overtime Report** — overtime minutes per employee per period (and totals).
4. **Employee Directory** — workforce export (code, name, dept, designation, manager, status).
5. **Project Assignment Report** — project ↔ member roster (project, member, role, dates).

> Reports is **not implemented in this pass** — spec only. Built after Dashboard.
> DWR enables a future **Work Summary / Hours-by-Project** report (not in the locked v1 catalogue; optional add-on).

### 2.4 Analytics — deferred

**Deferred** until Dashboard and Reports are complete. No backend, no UI in this scope. Nav stays "soon".

### 2.5 Settings

Tabbed settings surface:
1. **Users & Roles** — admin user management (in progress: list shipped; create/edit/detail pending).
2. **Security** — change own password (self-service) + admin reset password for another user.
3. **Attendance Policy** — workday minutes (default 480), overtime threshold (default 480), half-day minutes (240). Single-org config.
4. **Organization Settings** — org display name, timezone, (logo optional). Backs `PRODUCT_NAME` display.

Account removal model = **deactivate-only** (`is_active=false`); no hard delete (preserves history).
Roles stay a **fixed 4-role enum** in v1 (not configurable).

> **New backend needed for Settings:**
> - `PATCH /auth/me/password` (self password change — the deferred FD-3).
> - Attendance-policy + organization key/value config store + read/update endpoints.

---

## 3. RBAC — target matrix (v1)

Capabilities are enforced **server-side** (source of truth); the frontend `lib/rbac.ts` mirrors them for UX.

| Capability | admin | manager | employee | viewer | Notes |
|---|:--:|:--:|:--:|:--:|---|
| `user.manage` | ✅ | | | | Settings → Users |
| `employee.manage` | ✅ | | | | |
| `project.manage` | ✅ | | | | |
| `attendance.manage` | ✅ | ✅* | | | **Changed** — *manager scoped to team |
| `attendance.viewTeam` | ✅ | ✅ | | | |
| `report.submit` | ✅ | ✅ | ✅ | | **New** — create/edit/submit OWN work reports |
| `report.review` | ✅ | ✅ | | | Approve/reject work reports (already defined) |
| (read) | all | team-scoped | own | all read-only | List/detail scoping per module |

**Manager scope rule (cross-cutting — confirm):** a manager's "team" =
employees whose `employees.manager_id` = the manager's own employee id (direct reports).
This applies to attendance management, work-report review, and manager dashboard/report scoping.
*(This is the one open RBAC decision; see DWR spec §3. Recommended default = direct-reports.)*

---

## 4. Daily Work Reports — summary

The new priority module. Employees submit a **daily work report** (one per employee per day) made of
one or more **task lines**, each logging time against a project. Reports move through a
**draft → submitted → approved/rejected** workflow; managers/admins review.

Full specification + implementation plan: **[DAILY_WORK_REPORTS_SPEC.md](./DAILY_WORK_REPORTS_SPEC.md)**.

---

## 5. Out of scope (v1, unchanged)

Microservices · Kubernetes · event bus · AI · recruitment · biometric capture · multi-tenant ·
leave-request workflow · email-based password reset (no email infra) · audit log · Analytics.

---

## 6. Approval

Implementation does not begin until this spec + the DWR spec are approved. On approval, work starts
with the DWR backend (model → migration → service → router → tests → smoke), small commits per step.
