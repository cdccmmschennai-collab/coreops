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

---

## 13. Addendum — Full-Day / Split-Day periods (2026-07-19)

A report header now carries `report_mode` (`full_day` | `split_day`) and owns
one or two `work_report_periods` child rows (`full_day`, or `first_half` +
`second_half`) — still exactly ONE header per (employee, report_date). Each
period has its own status/location/remarks and a SERVER-derived
`work_fraction` (1.0 / 0.5) that scales NUMERIC benchmark targets
(`effective = base × fraction`, frozen at submit into
`benchmark_base_value_snapshot` / `benchmark_fraction_snapshot` /
`benchmark_value_snapshot`). Legacy full-day payloads translate into one
Full-Day period; historical `half_day` reports are backfilled as legacy
Full-Day periods at fraction 0.5 without guessing the worked half. Feature
flags: `REPORT_DAY_PARTS_ENABLED` / `NEXT_PUBLIC_REPORT_DAY_PARTS_ENABLED`
(both default off; behaviour is byte-identical while off).

Full design + file-by-file plan:
`docs/superpowers/plans/2026-07-19-split-day-work-reports.md`
(migration `0060_work_report_periods`).

---

## 14. Addendum — Numeric benchmark availability exception (2026-08-06)

### The problem

A numeric benchmark compares what an employee produced against a configured
daily target. It has no way to say "I finished everything there was to do, and
there was less of it than the target." Those days read as a shortfall
indistinguishable from underperformance, and the only way to explain them was a
free-text remark — which no calculation can safely read.

### The exception

`work_report_tasks.benchmark_exception_code` (migration
`0063_benchmark_exception_code`) is a nullable, structured reason. Phase 1
defines exactly one value:

`NO_FURTHER_AVAILABLE_WORK` — every TAG that was actually available for the
activity was completed, but fewer were available than the target.

`NULL` means "no exception" and is the default for every existing row: the
migration is purely additive, backfills nothing, and leaves historical reports
and their benchmark evaluation bit-for-bit unchanged.

VARCHAR(40) + CHECK rather than a native enum, following the
`benchmark_type` / `access_type` / `report_mode` precedent — widening the
allowed set later is an ALTER of one constraint.

### Validity conditions

An exception applies only when ALL of these hold
(`activity_master/benchmark_exception.py`):

| # | Condition |
|---|-----------|
| 1 | the code is a recognised exception code |
| 2 | `benchmark_type` is a pure numeric mode (`NUMERIC`, `NUMERIC_DAILY`) |
| 3 | `relevant_count_field` is exception-eligible — **Phase 1: `tags` only** |
| 4 | a positive benchmark target exists |
| 5 | an actual count is present (`0` counts — "none were available") |
| 6 | the actual is **strictly below** the target |

Task modes are excluded by condition 2, `TASK_WITH_QUANTITY` included: a task
carries a deadline, and its work is not per-day production.

The server never trusts the client. Validation runs twice:

- **on save** (`_validate_tasks`) — an unrecognised code is a 422; a known code
  on a sub-activity that cannot carry one (task mode, or a non-eligible unit) is
  silently **cleared**;
- **at submit** (`_apply_benchmarks`) — the authoritative check, made where the
  effective per-period target is frozen. An exception that has stopped
  describing reality (the actual reached the target, the target vanished, the
  sub-activity was reconfigured) is **cleared**, so no stale 100% survives an
  edit-and-resubmit.

Because the benchmark export reads submitted reports only, nothing that reaches
the report can bypass the submit-time check.

**The exception is structural, never textual.** No code path parses remark text.
An employee typing "no further tags were available" into their remark changes no
calculation and produces no system remark.

### Real actual vs effective actual

The distinction the whole feature rests on:

- **Real actual** — what the employee entered. Stored in the count column,
  displayed in ACTUAL COMPLETED, summed into the TOTAL row's ACTUAL cell. It is
  **never** overwritten with the target. Target 100 / actual 40 stays 40
  everywhere a number is stored or shown.
- **Effective actual** — calculation-only, never persisted and never given a
  cell: `target` on a valid exception row, the real actual otherwise. It feeds
  the percentages and the pending, and nothing else.

```
effective_actual = target   if the row has a valid exception
                 = actual   otherwise
```

Per detail row with a valid exception: ACHIEVEMENT 100%, DIFFERENCE 0%,
PENDING 0 — while ACTUAL still reads 40.

Per TOTAL row:

```
total_target    = Σ row targets
total_actual    = Σ real actuals            -> the ACTUAL COMPLETED cell
total_effective = Σ effective actuals       -> never a cell
achievement %   = total_effective / total_target      (uncapped, as before)
difference %    = ABS(achievement - 100%)
pending         = MAX(0, total_target - total_effective)
```

Overachievement is unaffected: a normal row contributes its real actual, so
140/100 still reads 140%.

### Benchmark Excel behaviour

- **Numeric only.** Task-mode activities no longer appear in the benchmark
  workbook at all — no detail row, no total row, no contribution to any target,
  actual, pending or percentage. Their textual cells ("FINISHED",
  "N DAYS OVERDUE") no longer sit in numeric columns, and a counted lumpsum no
  longer moves the achievement %. **Scope: this export only** — daily reports,
  alerts, overdue, task-status and performance views are untouched.
- **All exported text is uppercased** on the way into a cell. Numbers stay
  numeric, dates stay dates, percentages keep their format. The stored values in
  PostgreSQL are never modified.
- **Remarks.** An exception row's REMARKS cell is prefixed with the
  system-generated `[NO FURTHER TAGS WERE AVAILABLE FOR THIS ACTIVITY]`,
  followed by the employee's own remark after a ` | ` separator, or standing
  alone when there is none. Composition is a pure function of the code and the
  stored remark, so re-exporting can never duplicate the prefix, and the stored
  remark is never rewritten.
- **Amber cell.** ACTUAL COMPLETED → TAGS on an exception row is styled with
  fill `#FFF2CC`, font `#7F6000`, bold, and a thin amber border. It is an
  **accepted-exception** marker, not an error colour — deliberately not the red
  used for a shortfall. It lands on that ONE cell: never the whole row, never
  the target cell, never the pending cell, and it never changes the value under
  it. The TOTAL row's ACTUAL cell carries the same styling for any unit where at
  least one contributing row was an exception.
- **No column changes.** Nothing is added, removed, renamed or reordered. The
  effective actual is an intermediate, never a column — there is no "Evaluated
  Actual", "Exception", "Status" or "Exception Reason" column.

### Employee-facing UX

In the Daily Work Report activity form, a checkbox sits inside the Tags count
panel, below the actual Tags input:

> **No further tags were available for this activity**
> Select this only when all available tags for this activity have been completed.

It appears only when conditions 2–6 above hold, so it is invisible for task
activities, for Docs/BOM/Spares/Pages/Records, before a count is entered, and
once the count reaches the target. It is unchecked by default, restores when a
draft or reopened report is edited, and clears automatically when the activity,
sub-activity, benchmark or entered count stops satisfying those conditions. When
ticked it shows:

> AVAILABLE WORK COMPLETED - THIS ENTRY WILL BE EVALUATED AS TARGET ACHIEVED.

### Adding a unit later (Docs, BOM, Spares, Pages, Records)

Phase 1 is TAGS only, deliberately: the rule is only agreed for tags so far.
Widening it is a two-line change plus wording:

1. add the unit to `EXCEPTION_ELIGIBLE_COUNT_FIELDS` in
   `backend/app/modules/activity_master/benchmark_exception.py`, and add its
   system remark to `EXPORT_EXCEPTION_REMARK_BY_UNIT` (the export looks the
   wording up per unit — nothing hard-codes "tags");
2. add the same unit to `EXCEPTION_ELIGIBLE_COUNT_FIELDS` in
   `frontend/src/features/work-reports/benchmark-exception.ts`, and generalise
   the checkbox label/helper wording, which currently names tags.

Everything else — validation, effective-actual, aggregation, the amber cell and
the total-row styling — is already unit-generic and needs no change.

Files: `backend/app/modules/activity_master/benchmark_exception.py`,
`backend/alembic/versions/0063_benchmark_exception_code.py`,
`backend/app/modules/reports_export/export.py`,
`backend/app/modules/benchmarks/service.py`,
`frontend/src/features/work-reports/benchmark-exception.ts`.
Tests: `backend/tests/test_benchmark_exception.py`,
`frontend/src/features/work-reports/benchmark-exception.test.ts`.
