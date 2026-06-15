# ADR-003 — Project Progress and Submission Model

**Status:** Accepted  
**Date:** 2026-06-15  
**Supersedes:** Delivery Tracking (migration 0028) and Deliverables Module (migration 0029), both built on `feature/access`

**Amendments (accepted 2026-06-15):**
- Activity Progress must aggregate by `activity_type_id` FK, not free-text activity labels
- Project Submissions must carry a `status` field: `draft → submitted → approved / rejected`

---

## Context

CoreOps manages long-running engineering and data projects for infrastructure clients:

- FMTL (Facility Master Tag List)
- MTL (Master Tag List)
- BOM (Bill of Materials)
- CRS (Criticality Rating Sheet)
- Criticality Analysis
- Documentation
- QC (Quality Control)

These are continuous-effort projects where teams in Chennai perform work — populating databases, photographing assets, conducting quality checks — and periodically send completed quantity reports to the Qatar client office. A single project may run for months or years, with target dates that change as scope evolves.

### Why the previous direction failed

The Deliverables module (migration 0029) and Delivery Tracking fields (migration 0028) were built on the assumption that a project could be broken into named deliverables with fixed completion dates, similar to a software sprint or Jira-style tracking.

This assumption does not fit the business:

1. **No fixed scope decomposition.** There is no agreed list of "deliverables" per project at the start. Work is activity-based and continuous (e.g., "FMTL Data Population" runs until all tags are processed).

2. **Target dates are negotiated and change.** A planned completion date may shift multiple times as client requirements evolve, scope increases, or team capacity changes. A "deliverable is done" event is not meaningful when the project continues.

3. **Quantity, not task completion, is what the client receives.** Qatar receives formal submissions: "300 FMTL tags populated, 120 BOM documents processed this period." The currency is quantity × unit, not a deliverable status toggle.

4. **Progress is derived from approved work reports.** The system already captures individual work report entries by activity. Aggregate progress should be computed from these, not tracked in a separate deliverables table that must be manually reconciled.

---

## Decision

### 1. Deliverables are not the primary tracking mechanism

The `project_deliverables` table (migration 0029) and the `DeliveryBadge` / project health computation (migration 0028) are superseded by this ADR. They should not be extended. Whether they are removed from the schema or left dormant is a migration decision to be made separately; this ADR withdraws them from the product roadmap.

**The primary tracking model is:**

```
Project
  → Activities         (derived from approved work reports)
  → Progress           (aggregated: entries, hours, employees, date range)
  → Submissions        (formal periodic deliveries to Qatar)
  → Exports            (attendance, project progress, employee summaries)
```

### 2. Planned Completion Date is a planning estimate, not a contract

A `planned_completion_date` field is added to the `projects` table. It replaces `target_delivery_date` (migration 0028).

**Rules:**
- It is editable at any time by a Project Manager.
- Every change is logged: `old_date`, `new_date`, `changed_by` (employee FK), `reason` (free text), `changed_at` (UTC timestamp).
- No automated overdue status or health badge is derived from it. It is informational and historical.
- `actual_completion_date` (nullable) may be set when a project is formally closed, but this does not trigger workflow automation.

**Rationale:** Target dates in infrastructure asset management projects change as client scope evolves. Treating the date as a hard deadline creates false urgency signals and requires constant manual remediation. Recording the change history is far more useful than a green/amber/red health indicator.

### 3. Activity Progress is derived from approved work reports

The system already stores `daily_work_reports` rows with `activity` (free text describing the task performed) and `hours_worked`. When a report is approved, its entries become the authoritative record of work done.

**Activity Progress aggregation:**

For a given project and time range, group approved work reports by `activity` label and compute:

| Column | Source |
|---|---|
| Activity Name | `daily_work_reports.activity` |
| Total Entries | `COUNT(report rows)` |
| Total Hours | `SUM(hours_worked)` |
| Employees Worked | `COUNT(DISTINCT employee_id)` |
| First Activity Date | `MIN(report_date)` |
| Last Activity Date | `MAX(report_date)` |

**Important: aggregate by Activity Type ID, not free-text label.**

`work_report_tasks.activity_type` is currently a free-text `Text` column. Free-text aggregation produces the exact fragmentation problem described above ("FMTL Population" vs "FMTL DATA POPULATION" appearing as distinct activities). Therefore:

- Phase B migration will add `activity_type_id` (UUID FK → `activity_types.id`, nullable) to `work_report_tasks`.
- Activity Progress queries group by `activity_type_id` and display `activity_types.name` for each group.
- Rows where `activity_type_id IS NULL` (legacy or freeform entries) are excluded from project analytics or bucketed as "Unclassified" — decision deferred to Phase B.
- The existing free-text `activity_type` column is retained for display context but is not used as an aggregation key.

**Filters supported:** Day, Week, Month, Custom Range.

**Access:** Project Manager and Project Team Lead on the given project.

### 4. Submissions represent formal deliveries to the client

A `project_submissions` entity captures when the Chennai team formally sends work quantities to Qatar.

**`project_submissions` fields:**
- `project_id` FK
- `submission_date` (the date the submission was sent)
- `period_start`, `period_end` (the work period covered)
- `status` — enum: `draft | submitted | approved | rejected`
- `notes` (free text)
- `submitted_by` (employee FK)
- `reviewed_by` (employee FK, nullable — set when Qatar approves/rejects)
- `reviewed_at` (nullable timestamp)
- `review_note` (free text, nullable)
- `created_at`

**Submission status lifecycle:**

```
draft → submitted → approved
                 ↘ rejected
```

PM or team lead creates a draft submission, reviews it, then marks it `submitted` to signal it has been sent to Qatar. Qatar-side review (approve/reject) is recorded manually — there is no external webhook. This supports an eventual client portal without requiring one now.

**`project_submission_items` fields:**
- `submission_id` FK
- `activity_type_id` FK → `activity_types.id` (nullable; allows freeform items in V1)
- `activity_label` (free text — display label, required; snapshot for when activity type is renamed/deleted)
- `quantity` (integer)
- `unit` (free text, e.g., "Tags", "Documents")

**V1 is manual entry.** Quantities are entered by the PM or team lead; they are not computed from work report counts. Automatic quantity calculation from approved reports is deferred to V2 — the data structures will support it but the feature is not built yet.

**Rationale:** Submissions are a business communication artefact. They exist even if the underlying work report data does not perfectly map to quantities (e.g., partial counts, rework, pre-system work). Manual entry preserves accuracy for the client-facing record.

### 5. Permission model

| Feature | Admin | Project Manager | Team Lead (on project) | Member (on project) |
|---|---|---|---|---|
| Edit Planned Completion Date | Yes | Yes | No | No |
| View Planned Date Change Log | Yes | Yes | Yes | No |
| View Activity Progress | Yes | Yes | Yes | No |
| Create / Edit Submissions | Yes | Yes | No | No |
| View Submissions | Yes | Yes | Yes | No |
| Attendance Export | Yes | Yes | Yes | Yes |
| Project Export | Yes | Yes | Yes | No |
| Employee Export | Yes | Yes | Yes | Yes |

Team Lead access is scoped to projects they are explicitly a member of with `role = team_lead`.

### 6. Project Timeline Events

A lightweight timeline records structural changes to a project. Events are append-only and never edited.

| Event Type | Triggered By |
|---|---|
| `project_created` | Project creation |
| `planned_date_changed` | PM edits planned completion date |
| `member_added` | Employee added to project |
| `member_removed` | Employee removed from project |
| `submission_created` | New submission saved |
| `submission_updated` | Submission edited |

Timeline is visible to Project Manager and Team Lead.

### 7. Export strategy

Three export categories are defined. All exports are XLSX or CSV; format to be determined per category in implementation.

**Attendance Export** — available to all roles. Covers employee attendance records by month or custom date range.

**Project Export** — available to Project Manager and Team Lead (scoped to their projects). Filters: daily, weekly, monthly, custom range. Columns: Employee, Activity, Hours, Report Count. Source: approved work reports linked to the project.

**Employee Export** — available to all roles. Filters: daily, weekly, monthly, custom range. Columns: Attendance records, Work reports, Activities performed, Hours logged.

Async generation via Celery (pattern established by the existing `export_jobs` table from migration 0024) should be reused. Do not build a new export queue.

---

## Implementation Phases

Revised order — submissions are the core business process; analytics are derived from existing data and can follow:

| Phase | Scope | Status |
|---|---|---|
| A | Planned Completion Date + Change Log | Accepted — implement next |
| D | Project Timeline | Not started — depends on Phase A (planned_date_changed event) |
| C | Project Submissions | Not started — depends on Phase D (submission_created event) |
| B | Activity Progress module | Not started — depends on Phase C (activity_type_id FK migration) |
| E | Exports | Not started — depends on Phase B |

Each phase gate is explicit. Phase A must be reviewed and tested before Phase D begins.

---

## Consequences

**Positive**
- Model matches how the business actually works: continuous activity, periodic client submissions, fluid target dates
- Activity Progress is derived from the existing approved-report data — no duplicate entry or reconciliation required
- Submission records give Qatar-facing audit trail without coupling to internal work report structure
- Planned date change log provides historical accountability without artificial urgency signals

**Negative / Trade-offs**
- Activity names are free text in V1; cross-project activity aggregation (e.g., "all FMTL Population hours across all projects") is not reliable until normalisation is added
- Submission quantities are manually entered; they may diverge from what work reports would compute — this is intentional for V1
- Migrations 0028 and 0029 are now legacy; schema cleanup (drop or ignore) must be decided before V2 to avoid confusion

---

## What is NOT in scope

- Overdue workflows, escalation triggers, or health badges (explicitly rejected — see Section 2)
- Sprint or iteration planning
- Automatic quantity calculation from work reports (V2)
- Client portal or external submission workflow
- Jira / PM tool integration
