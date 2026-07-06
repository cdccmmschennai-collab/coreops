# CoreOps — Project Activity Assignment Architecture (Design Spec)

**Status:** Revised for approval
**Date:** 2026-07-05 · **Revised:** 2026-07-06
**Constraint:** Live production system. Every phase is additive, backward-compatible, independently deployable, rollback-safe, zero-downtime, and preserves production data. No implementation code until approved.

> **Revision 2026-07-06 (business-workflow correction).** The staffing model is tightened to the real workflow:
> 1. PM manages projects and assigns **exactly one Head per project** — and nothing else about staffing.
> 2. The **Head manages all activity assignments** within the project.
> 3. Each activity has **exactly one Lead** (was: multiple Leads).
> 4. Each activity has **multiple Contributors**.
> 5. **QC is an additive responsibility** (a flag), not an exclusive role: it can sit on the Lead, a Contributor, or any employee assigned to that activity.
> 6. **Activity Leads may add Contributors and QC only within their own activity.**
> 7. **PM does not manage activity assignments directly.**
>
> Net data-model change: `project_activity_members.role ∈ {lead, contributor}` (QC dropped from the enum) plus a new `is_qc` boolean; a partial-unique index enforces one Lead per activity. Permissions, APIs, and the frontend (now an activity-grouped member view) are updated below. Migrations already shipped in Phase 2 are unaffected.

---

## 1. Objective

Replace the standalone Task-assignment concept with a **Project Activity Assignment** architecture: employees are assigned, per project, to the **existing** activities in `activity_master`, with a role (Lead / Contributor / QC). Reports, benchmarks, and exports already key off activities, so this layer makes "who works on what" structural and reportable without a parallel task system.

## 2. Global roles (unchanged, non-negotiable)

Only `project_manager` (PM) and `employee` exist as global roles / JWT roles. **Head, Activity Lead, Contributor, QC are per-project/per-activity assignments**, resolved from the DB per request. The same employee can be Head in Project A, Lead in Project B, Contributor in Project C — with no change to their global role.

## 3. Confirmed decisions

1. Live data → every change additive with backfill + rollback + integrity checks.
2. **One Head per project**, assigned by the PM. The Head **manages all activity assignments** within the project and absorbs the `project_managers` notification-routing role (that table is **deprecated in place**, deleted only after production verification).
3. **PM manages projects only** — create/edit/archive projects, manage employees, approve leave, and assign the Head. **PM does not manage activity assignments** (no adding activities, no assigning Leads/Contributors/QC).
4. Activities/sub-activities are the **existing `activity_master`** — no new activity table.
5. New **`project_activity_members`** join is the only new core table.
6. **Assignment is at the activity level** (`activity_master.level='activity'`); a report's `sub_activity_id` rolls up to its parent activity for the "is assigned?" check and for grouping.
7. **Exactly one Lead per activity** (partial-unique index), **multiple Contributors**. The Lead role is the base staffing role alongside `contributor`.
8. **QC is an additive responsibility, not an exclusive role** — an `is_qc` boolean on an activity assignment. It may be set on the Lead, a Contributor, or any employee assigned to that activity (to make a not-yet-assigned employee a QC, they are added as a Contributor with `is_qc=true`). `role ∈ {lead, contributor}` only.
9. **Head assigns/replaces the Lead** and may assign/remove Contributors and toggle QC on **any** activity in the project. **Activity Leads may add/remove Contributors and toggle QC only within their own activity.**
10. `project_members` stays the **visibility backbone**, auto-maintained from assignments (Head + every activity assignment).
11. **PM never submits work reports.** QC submits their own reports like any employee and is **not** an approver.
12. **Report review = PM + Head only.** Activity Leads view their activity's reports but do not review.
13. Reports need **no schema change** (activity = parent of the existing `sub_activity_id`).

## 4. Data model

### 4.1 `project_activity_members` (new core table)
| column | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `project_id` | uuid FK→`projects` (CASCADE) | |
| `activity_id` | uuid FK→`activity_master` (RESTRICT) | must be a `level='activity'` node |
| `employee_id` | uuid FK→`employees` (RESTRICT) | |
| `role` | enum `lead \| contributor` | base staffing role; QC is **not** a role value |
| `is_qc` | bool, default `false` | additive QC responsibility; may be `true` on a lead or a contributor |
| `created_by` | uuid | |
| timestamps | | |

- **Unique** `(project_id, activity_id, employee_id)` — one assignment (hence one base role) per person per activity per project.
- **Partial-unique** `(project_id, activity_id) WHERE role='lead'` — **at most one Lead per activity**. "Exactly one" (an activity is only staffed once it has a Lead) is enforced in the service: the Lead is the anchor assignment; the Head sets it first, and the last Lead cannot be removed while the activity still has members (reassign instead).
- **QC (`is_qc`)** may be `true` on any assignment (lead or contributor); it is never a standalone row. To make a not-yet-assigned employee a QC, insert a `contributor` row with `is_qc=true`. QC count per activity is **0..N** by default (a single-QC-per-activity partial-unique index can be added later if the business wants exactly one).
- Indexes: `(project_id)`, `(activity_id)`, `(employee_id)`, `(project_id, activity_id)`.
- A project "has" an activity when ≥1 assignment exists for it (no separate enablement table initially — YAGNI).
- Service-layer guards: reject `activity_id` whose `level != 'activity'`; reject a second `role='lead'` on the same activity (DB backstops via the partial-unique index).

### 4.2 Head ownership
- `projects.head_employee_id` (nullable FK→employees, SET NULL). One Head/project, assigned by PM. Project owner; notification-routing target.

### 4.3 Visibility backbone
- `project_members` unchanged as the source of project visibility. Any assignment (Head or `project_activity_members`) **auto-maintains** a `project_members('member')` row, **reference-counted**: removed when the person's last assignment on that project is removed, unless Head or explicitly added. Logic lives only in the assignment service (single source of truth). Keeps all existing project-scoped read queries working unchanged.

### 4.4 Deliverables → activity-aware
- Add nullable `project_deliverables.activity_id` (FK→`activity_master`) for per-(project, activity) targets. Existing project-level deliverables keep `activity_id = NULL`. "Completed" is summed from reports (§7); "remaining" = target − completed.

### 4.5 Reports (unchanged)
- `work_report_tasks` keeps `project_id` + `sub_activity_id`. Activity = `parent(sub_activity_id)`. No column added.

### 4.6 Relationships
```
projects ──1:1── head_employee_id ─▶ employees
projects ──1:*── project_activity_members ─*:1─▶ activity_master (activity node)
                          └─────────────── *:1─▶ employees   (role lead|contributor, +is_qc flag)
projects ──1:*── project_members            (visibility backbone, auto-maintained)
work_report_tasks ─*:1─▶ activity_master(sub_activity) ─parent─▶ activity  (rollup)
project_deliverables ─*:1─▶ activity_master (optional activity_id)
```

## 5. Permissions — central helper (`app/core/authz.py`)

QC is a flag, not a distinct actor; the "QC" column describes the report-scope a QC-flagged member gets. "own activity" = the activity the person is Lead of.

| Action | PM | Head (project) | Lead (own activity) | Contributor | QC (flag) |
|---|---|---|---|---|---|
| Create/edit/archive projects, manage employees, approve leave | ✅ | ❌ | ❌ | ❌ | ❌ |
| Assign/replace Head | ✅ | ❌ | ❌ | ❌ | ❌ |
| Add activity to project; assign/replace its **Lead** | ❌ | ✅ | ❌ | ❌ | ❌ |
| Assign/remove **Contributors** + toggle **QC** on an activity | ❌ | ✅ (any activity) | ✅ (own activity) | ❌ | ❌ |
| Review reports (approve/reject/request-edit) | ✅ | ✅ | ❌ | ❌ | ❌ |
| Submit own reports (assigned activities) | ❌ never | ✅ | ✅ | ✅ | ✅ |
| View activity reports | all | all in project | own activity | own | own activity |
| View project / members / timeline | ✅ | ✅ | ✅ | ✅ | ✅ |

PM retains **read** visibility of everything (projects, activities, members, reports) but performs **no** activity-staffing writes.

Helper API (`app/core/authz.py`): `can_view_project`, `can_manage_project` (PM), `can_assign_head` (PM), `can_manage_activity(project)` (Head — add activity / assign-replace Lead), `can_assign_contributor(activity)` (Head, or the Lead of that activity — also gates QC toggling), `can_review_report` (PM + Head). Ownership checks up the chain (PM ⊃ Head for reads; Head ⊃ Lead for staffing). Replaces the ~13 duplicated `_assert_can_*` helpers.

## 6. APIs (new/changed)
- `PUT /projects/{id}/head` — **PM** sets/replaces Head (+ timeline `HEAD_ASSIGNED/CHANGED`).
- `GET /projects/{id}/activities` — activities used by the project, each with its single **Lead**, **Contributors**, and which members are **QC** (`is_qc`), plus counts.
- `POST /projects/{id}/activities/{activity_id}/members` `{employee_id, role, is_qc?}` — assign. `role ∈ {lead, contributor}`. Permission: `role='lead'` → **Head only** (replaces the existing Lead; backed by the partial-unique index); `role='contributor'` (and any `is_qc` toggle) → **Head or the Lead of that activity**.
- `PATCH /projects/{id}/activities/{activity_id}/members/{employee_id}` `{role?, is_qc?}` — change base role and/or toggle QC (same permission split: promoting to `lead` is Head-only).
- `DELETE /projects/{id}/activities/{activity_id}/members/{employee_id}` — Head (any) or Lead (own activity); the last Lead cannot be removed while members remain.
- `GET /projects/{id}/activities/{activity_id}/stats` — activity-wise counts/totals/pending/benchmark.
- `GET /me/activities` — caller's assigned activities across projects (with base role + `is_qc`).
- Timeline events: `HEAD_ASSIGNED/CHANGED`, `ACTIVITY_LEAD_ASSIGNED/CHANGED`, `ACTIVITY_MEMBER_ASSIGNED/REMOVED`, `ACTIVITY_QC_SET/CLEARED`.
- Submission gate (Phase 6): validate author assigned to the report line's activity.
- Project/activity responses return the caller's effective role for frontend gating: `my_project_role ∈ {pm, head, member, none}`; per activity `my_activity_role ∈ {lead, contributor, none}` plus `my_is_qc`.

## 7. Reporting flow, statistics & deliverables
- **Submit:** Contributor picks Project + Activity (assigned) + Sub-Activity + counts/minutes; backend derives activity = `parent(sub_activity)`; asserts assignment (enforced Phase 6); submit freezes benchmark snapshot (unchanged).
- **Stats (pure reads):** group `work_report_tasks` by parent activity → report counts, summed counts/minutes, benchmark comparison; per (project, activity, employee) and activity totals. No schema change.
- **Deliverables:** per-(project, activity) targets via `deliverables.activity_id`; completed = summed report counts; Head sees target/completed/remaining per activity ("which activity is behind?").
- **Review:** PM + Head across the project. **Export:** unchanged (already activity/sub-activity grouped).

## 8. Frontend
**Guiding principle:** the project detail page's staffing is an **activity-grouped member view**, not a flat project-members list. Keep it visually consistent with the current project page (same cards/badges/section headers) and simple — one section per activity, members listed under their activity by role.

The project detail page renders one of three role-specific views, all sharing the same **Head** section on top and the same **activity-grouped member list** below. Keep it plain — grouped text/badges, no heavy tables — consistent with the existing project page.

**Common layout (all roles):**
```
Head
----
Santhosh

Activities
----------
MTL
  Lead
    Saagar
  Contributors
    Santhosh
    Alex
  QC
    Alex
------------------------
FMTL
  Lead
    Dinesh
  Contributors
    Rahul
    Bob
  QC
    Rahul
```
QC lists the members of that activity whose `is_qc = true` (a person can appear under both their base role and QC, e.g. a Lead who is also QC).

**PM Project View:** Head section shows the current Head with an **Assign / Replace Head** control only (employee picker over **any** employee). All activities + members render **read-only**. **No** activity-staffing controls.

**Head Project View:** Head section shows the Head (read-only for the Head themselves). One **single assignment form** above the grouped list:
- Employee dropdown (any employee) · Activity dropdown (existing `activity_master` activities) · Role dropdown (**Lead** or **Contributor**) · **QC** checkbox · **Add** button.
- On submit, only the **affected activity's section** re-renders (optimistic/targeted update), not the whole page.
- Assigning `Lead` to an activity that already has one **replaces** it. Per-member remove/QC-toggle affordances appear inline in each activity group.

**Lead View:** sees **only their own activity** (Head section still visible, read-only). Same assignment form but with **no Activity dropdown** (the activity is fixed to theirs); Role dropdown is effectively Contributor + a QC checkbox. The Lead may add/remove Contributors and toggle QC within that activity, and cannot change the Lead.

- **Activity detail (drill-in):** members, per-activity stats, reports (grouped by member), deliverables (Phase 4-5).
- **Dashboards:** Head → project's activities with staffing + report/deliverable progress; Lead → only their activity; Contributor → "My assigned activities" → sub-activities → submit.
- **Reports view:** grouped by activity → employee → totals.
- Gating comes from API effective roles (`my_project_role`, `my_activity_role`, `my_is_qc`); `rbac.ts` keeps only the two global gates (PM / employee).

## 9. How this replaces the Task module
The Task module tracked ad-hoc "assign a unit of work to an employee" via a free-floating `tasks` row + status flips, disconnected from reports/benchmarks. Project Activity Assignment expresses "who works on what" **structurally** — an employee assigned to a project's activity with a role, whose daily reports (already keyed to that activity's sub-activities) *are* the work record, with benchmarks/QC/rollups for free. Task removal (Phase 1) clears the superseded mechanism.

## 10. Migration risks (live data)
- **R1** — assignment table starts empty; the submission gate must be **added but OFF** until Heads populate assignments (else daily submission breaks). Enforced in Phase 6.
- **R2** — PM-authored historical reports: preserve read-only; disable PM submit going forward.
- **R3** — reference-counted visibility rows: centralize + unit-test (orphan/leak hazard).
- **R4** — Head vacancy after migration: routing falls back to `reporting_pm_id` → PM.
- **R5** — deprecate `project_managers` in place; delete only in Phase 6 after verification.

## 11. Phased implementation plan (each additive, independently deployable, rollback-safe)
1. **Phase 1 — Remove Task module** (prerequisite; detailed plan: `docs/superpowers/plans/2026-07-05-phase1-remove-task-module.md`).
2. **Phase 2 — Head ownership:** `head_employee_id` + `authz.py` + Head-assignment API + timeline + relax timeline view to members.
3. **Phase 3 — Assignment layer:** `project_activity_members` (`role ∈ {lead, contributor}` + `is_qc` bool; partial-unique one-Lead-per-activity) + Head-managed assign/replace-Lead, add/remove-Contributor, toggle-QC APIs (Lead scoped to own activity) + auto-maintain `project_members` visibility + timeline events + the **activity-grouped member UI** on project detail (§8).
4. **Phase 4 — Read models & dashboards:** activity-grouped reports, activity-wise stats, Head/Lead/Contributor dashboards.
5. **Phase 5 — Activity-wise deliverables:** `deliverables.activity_id` + target/completed/remaining.
6. **Phase 6 — Enforce submission gate + retire legacy** (`project_managers`, old `team_lead` role, `project_activities.assigned_to_id`) after production verification.

## 12. Future scalability
Assignments are a thin join; union scoping over `project_members` + `project_activity_members` is trivial at company scale (resolve a user's roles once per request). New master activities/sub-activities are instantly assignable — no migration. Optional `project_activity_targets`/enablement table slots in later for pre-staffing or period targets.

## 13. Out of scope (explicitly untouched)
The existing `project_activities` "Deliverable Activity Tracker" table/module/tab is unrelated to this model and is left as-is. `work_report_tasks`, benchmarks, employee-performance `tasks-tab` stay (naming collisions, part of the surviving reporting workflow).
