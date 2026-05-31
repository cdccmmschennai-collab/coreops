# Daily Work Reports (DWR) — Module Specification & Implementation Plan

**Status:** Draft for approval · **Date:** 2026-06-01
**Parent:** [PRODUCT_SPEC_V1.md](./PRODUCT_SPEC_V1.md) · **Priority:** Next module
**Conventions:** mirrors Employees / Projects / Attendance exactly (modular monolith, thin router → service,
SQLAlchemy 2.0, UUID PK, `TimestampMixin`, audit `created_by`/`updated_by`, partial-unique natural key,
enum `values_callable`, uniform error envelope, incremental reversible Alembic migration).

---

## 1. Concept

An employee logs what they worked on each day. A **Daily Work Report** is a *header* (one per
employee per calendar date) containing one or more **task lines**, each attributing time to a
project with a description. Reports are submitted for review; managers/admins approve or reject.

- Grain: **one report header per `(employee, report_date)`** (enforced unique).
- A report has **≥ 1 task line** to be submittable; each line ties to a project + minutes + description.
- `total_minutes` on the header is **derived** = sum of line minutes (read-only, like attendance).
- Workflow status drives editability and who can act.

> **Design choice — header + line items (recommended).** Chosen over a single free-text report so the
> data feeds project-hours reporting and the manager/employee dashboards cleanly. If the PO prefers a
> simpler single-summary model for v1, that is the one open structural decision (§11, D-DWR-1).

---

## 2. Data model

### 2.1 `daily_work_reports` (header)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | `UUIDMixin` |
| `employee_id` | UUID FK → `employees.id` (RESTRICT) | author (the worker) |
| `report_date` | DATE, not null | the work day |
| `status` | enum `work_report_status` | `draft` \| `submitted` \| `approved` \| `rejected`; server_default `draft` |
| `summary` | TEXT, nullable | optional overall note (≤ 2000 chars) |
| `total_minutes` | INT, not null, default 0 | **derived** = Σ task minutes |
| `submitted_at` | TIMESTAMPTZ, nullable | set on submit |
| `reviewed_by` | UUID, nullable | reviewer user id |
| `reviewed_at` | TIMESTAMPTZ, nullable | set on approve/reject |
| `review_note` | TEXT, nullable | required on reject (≤ 1000 chars) |
| `created_by` / `updated_by` | UUID, nullable | audit |
| `created_at` / `updated_at` | TIMESTAMPTZ | `TimestampMixin` |

**Constraints / indexes**
- Partial-unique natural key: `UNIQUE (employee_id, report_date)` *(no soft-delete on this table — drafts are hard-deletable; submitted+ are immutable records).*
- `Index (employee_id, report_date)`; `Index (status)`; `Index (report_date)`.
- `CHECK (total_minutes >= 0 AND total_minutes <= 1440)`.

> **Soft-delete:** intentionally **not** used here (unlike employees/projects). Reports are operational
> records; only `draft` reports may be hard-deleted by their author. Submitted/approved/rejected are retained.

### 2.2 `work_report_tasks` (lines)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `report_id` | UUID FK → `daily_work_reports.id` (CASCADE) | parent header |
| `project_id` | UUID FK → `projects.id` (RESTRICT) | project worked on |
| `description` | TEXT, not null | what was done (≤ 2000 chars) |
| `minutes_spent` | INT, not null | `CHECK (1 ≤ minutes_spent ≤ 1440)` |
| `created_at` | TIMESTAMPTZ | |

**Indexes:** `Index (report_id)`, `Index (project_id)`. Lines are replaced wholesale on edit
(delete-and-reinsert within the header's PATCH), so no per-line audit columns.

### 2.3 Status enum & transitions

```
draft ──submit──▶ submitted ──approve──▶ approved   (terminal)
  ▲                   │
  └────reject─────────┘ (reject sets status=rejected; rejected is editable → back to draft on next edit/submit)
```

- `draft`: editable & deletable by author.
- `submitted`: locked for the author; awaiting review.
- `approved`: terminal; immutable.
- `rejected`: editable by author again (re-submit allowed); reviewer note explains why.

Invalid transitions return **422** (mirrors attendance's "prevent invalid state transitions").

---

## 3. RBAC rules

Capabilities (added to `lib/rbac.ts` + enforced server-side):
- **`report.submit`** = `admin`, `manager`, `employee` — create/edit/submit/delete **own** reports.
- **`report.review`** = `admin`, `manager` — approve/reject (already defined in `rbac.ts`).

| Action | admin | manager | employee | viewer |
|---|:--:|:--:|:--:|:--:|
| Create / edit / submit / delete **own** draft | ✅ | ✅ | ✅ | — |
| View own | ✅ | ✅ | ✅ | ✅ |
| View **team** reports | ✅ (all) | ✅ (team) | — | ✅ (all, read-only) |
| Approve / reject | ✅ (all) | ✅ (team) | — | — |
| Edit someone else's report content | ❌ | ❌ | ❌ | ❌ |

**Scoping** (uses the existing `_current_employee(db, actor)` helper to map the JWT user → employee):
- **employee** → only rows where `employee_id == me`.
- **manager** → own rows **plus** team rows where the author's `employees.manager_id == me`
  (direct reports). Review limited to the same team set.
- **admin** → all. **viewer** → read-only all.

> **Open decision (D-DWR-2):** manager scope = direct reports (`manager_id`) — recommended and
> consistent with the cross-cutting rule in the product spec. Alternative (project-membership based)
> is possible but creates a different scope rule than the rest of the system. Confirm before build.

No-one may edit another user's report content. Reviewers act only via approve/reject (+ note).

---

## 4. Backend endpoints

Base path `/work-reports` (router mounted like attendance). All return the uniform error envelope.

| Method | Path | Capability | Body / params | Result |
|---|---|---|---|---|
| GET | `/work-reports` | authenticated (scoped) | `employee_id, project_id, status, from, to, limit, offset` | `WorkReportPage` (scoped) |
| POST | `/work-reports` | `report.submit` (self) | `WorkReportCreate` (`report_date`, `summary?`, `tasks[]`) | `WorkReportOut` (status=`draft`) |
| GET | `/work-reports/{id}` | scoped read | — | `WorkReportOut` (with tasks) |
| PATCH | `/work-reports/{id}` | author, status ∈ {draft, rejected} | `WorkReportUpdate` (`summary?`, `tasks[]?`) | `WorkReportOut` |
| POST | `/work-reports/{id}/submit` | author, status ∈ {draft, rejected} | — | `WorkReportOut` (status=`submitted`) |
| POST | `/work-reports/{id}/approve` | `report.review` (team) | — | `WorkReportOut` (status=`approved`) |
| POST | `/work-reports/{id}/reject` | `report.review` (team) | `{ review_note }` | `WorkReportOut` (status=`rejected`) |
| DELETE | `/work-reports/{id}` | author, status == `draft` | — | `204` |

**Schemas** (pydantic, mirror attendance):
- `WorkReportTaskIn { project_id, description, minutes_spent }`
- `WorkReportTaskOut { id, project_id, description, minutes_spent }`
- `WorkReportCreate { report_date, summary?, tasks: [WorkReportTaskIn] (≥1) }`
- `WorkReportUpdate { summary?, tasks?: [WorkReportTaskIn] }`
- `WorkReportReject { review_note }`
- `WorkReportOut { id, employee_id, report_date, status, summary, total_minutes, tasks[], submitted_at, reviewed_by, reviewed_at, review_note, created_at }`
- `WorkReportPage { items[], total, limit, offset }`

`total_minutes` is computed server-side from tasks on create/edit (never accepted from client),
identical in spirit to attendance's derived minutes.

---

## 5. Workflow

1. **Create (draft)** — employee POSTs a report for a date with ≥1 task. Status `draft`.
2. **Edit** — author PATCHes while `draft`/`rejected` (tasks replaced wholesale; `total_minutes` recomputed).
3. **Submit** — author POSTs `/submit`; requires ≥1 task; status → `submitted`, `submitted_at` set. Now read-only to author.
4. **Review** — a manager (team) / admin opens it and either:
   - **Approve** → status `approved`, `reviewed_by/at` set. Terminal.
   - **Reject** → requires `review_note`; status `rejected`, `reviewed_by/at` set. Author may edit & resubmit.
5. **Delete** — only the author, only while `draft` (hard delete). Submitted+ are retained.

Guards (→ 422 unless noted):
- Submitting/approving/rejecting from a non-allowed status.
- Approve/reject by a reviewer outside the author's team (→ **403**).
- Editing/deleting a non-`draft`(/`rejected`) report, or by a non-author (→ **403**).

---

## 6. Validation rules

**Header**
- `report_date` required; **not in the future** (`> today` → 422); within the **edit window** = current + previous month (older dates → 422; matches attendance policy).
- One report per `(employee, report_date)` → duplicate **409** (uniform envelope, `code=conflict`).
- `summary` ≤ 2000 chars.
- `review_note` required & non-empty on reject (≤ 1000 chars).

**Tasks**
- ≥ 1 task required to **submit** (create may allow draft with ≥1; empty drafts disallowed — keep ≥1 on create for simplicity).
- Each `minutes_spent` integer in `[1, 1440]`.
- **Σ minutes ≤ 1440** per report (can't log more than a day) → 422.
- `description` required, 1–2000 chars.
- `project_id` must reference an **existing, non-archived** project → 422 (`unknown/invalid project`).
- **Project membership (D-DWR-3, recommended):** the author must be a member of the project
  (`project_members`) → else 422. Ties DWR to assignments and the Project Assignment Report. *(Confirm; can relax to "any active project" if too strict for v1.)*

**Email/dup/validation** all surfaced through the standard `AppError` envelope; frontend maps
409 → field/top, 422 → top/field, 403 → guard, 404 → NotFound, 401 → global.

---

## 7. Frontend pages

New nav item **"Work Reports"** (`/work-reports`), icon e.g. `ClipboardList`, visible to all roles
(content scoped). Reuses Employees/Projects/Attendance frontend architecture exactly
(`features/work-reports/{types,keys,schemas,api,hooks}.ts` + `components/`, generated OpenAPI types,
TanStack Query, RHF + Zod, `RequireCapability`, URL-driven list state).

| Route | Purpose | Notes |
|---|---|---|
| `/work-reports` | List (role-scoped) | Filters: status, project, date range; employee filter for admin/manager; default scope = mine for employee, team for manager, all for admin. Columns: Date · Employee (mgr/admin) · Status · Total (hh:mm) · Tasks (count). Pagination, loading/error/empty. |
| `/work-reports/new` | Create draft | `RequireCapability("report.submit")`. Date + summary + repeatable task rows (project select, description, minutes). Live total. |
| `/work-reports/[id]` | Detail | Header + task table + status badge + review panel. Reviewers (team) see **Approve/Reject** (reject opens note dialog). Author sees **Edit/Submit/Delete** while draft/rejected. |
| `/work-reports/[id]/edit` | Edit draft/rejected | Author only; same form as new (date read-only). |

UI states reuse: `StatusBadge` (draft=neutral, submitted=info, approved=success, rejected=danger),
`TableSkeleton`, `EmptyState`, `ErrorState`, `Pagination`, `Select`, `DropdownMenu`, dialogs.
Project select reuses a `useProjectOptions` (mirror of `useEmployeeOptions`), filtered to active projects.

---

## 8. Reporting implications

- DWR introduces **logged hours per project per employee**, enabling a future
  **Work Summary / Hours-by-Project** report (period → employee × project → minutes). *Not in the
  locked v1 Reports catalogue; flagged as an optional add-on once Reports ships.*
- **Project Assignment Report** can be enriched later with "logged hours" per member.
- All DWR exports would follow the locked **CSV + XLSX** formats and synchronous generation.

No new Reports work in this pass — these are forward links only.

## 9. Dashboard implications

- **Employee dashboard** — "submitted reports" tile: this-week counts of `draft` / `submitted` / `approved`; quick link to `/work-reports/new`.
- **Manager dashboard** — "pending reviews" tile: count of team reports in `submitted`; links to a filtered list (`?status=submitted`).
- **Admin dashboard** — submission-compliance signal: # reports submitted today vs active headcount (optional KPI).

These tiles are specified here but built in the Dashboard pass, not now.

---

## 10. Implementation plan (phased, small commits)

**Backend (mirror Attendance build order):**
1. **Models** — `daily_work_reports` + `work_report_tasks` + enum.
2. **Migration** — Alembic, reversible; verify up → down → up.
3. **Schemas** — create/update/out/page/reject + task in/out.
4. **Service** — RBAC scoping (`_current_employee`), derived `total_minutes`, transition guards, validation, project/membership checks.
5. **Router** — thin; the 8 endpoints in §4.
6. **Tests** — pytest: CRUD, scoping per role, transitions (valid + invalid), validation (future date, >1440, duplicate, unknown/archived project, membership), review by non-team → 403. Target: keep the suite green (currently 83 passing).
7. **Smoke** — live: create → submit → approve/reject as seeded users.

**Frontend (mirror Attendance, after backend live):**
- Phase A — regen OpenAPI types; data layer (`types/keys/schemas/api/hooks`) + `useProjectOptions`.
- Phase B — list page (scoped, filters, pagination, states).
- Phase C — detail page + review actions (approve/reject dialog) + author actions.
- Phase D — create/edit form (repeatable task rows, live total).
- Phase E — add `report.submit` capability + sidebar nav item; verify typecheck + build + Docker routes.

Each phase: typecheck/tests → small commit → report (files, commands, results, hash). Phases not combined.

**Infra/RBAC touchpoints:** add `report.submit` to `lib/rbac.ts`; add sidebar "Work Reports";
no new npm packages; ports unchanged (FE 3100 / BE 8100 / PG 5433 / Redis 6381).

---

## 11. Open decisions (confirm before build)

- **D-DWR-1 — Structure:** header + task lines *(recommended)* vs single free-text summary report.
- **D-DWR-2 — Manager scope:** direct reports via `employees.manager_id` *(recommended)* vs project-membership based.
- **D-DWR-3 — Project membership required** on each task line *(recommended)* vs any active project allowed.
- **D-DWR-4 — Edit window:** current + previous month *(recommended, matches attendance)* vs unrestricted vs current month only.
- **D-DWR-5 — Resubmission:** rejected → editable & resubmittable *(recommended)* vs rejected is terminal (new report required).

Defaults (the *recommended* option) apply where not answered.

---

## 12. Approval

No code until this spec is approved. On approval, implementation begins at §10 step 1 (models),
one small commit per step, with a per-step report.
