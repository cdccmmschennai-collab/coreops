# CoreOps — Project Activity Assignment Architecture (Design Spec)

**Status:** Finalized for approval
**Date:** 2026-07-05
**Constraint:** Live production system. Every phase is additive, backward-compatible, independently deployable, rollback-safe, zero-downtime, and preserves production data. No implementation code until approved.

---

## 1. Objective

Replace the standalone Task-assignment concept with a **Project Activity Assignment** architecture: employees are assigned, per project, to the **existing** activities in `activity_master`, with a role (Lead / Contributor / QC). Reports, benchmarks, and exports already key off activities, so this layer makes "who works on what" structural and reportable without a parallel task system.

## 2. Global roles (unchanged, non-negotiable)

Only `project_manager` (PM) and `employee` exist as global roles / JWT roles. **Head, Activity Lead, Contributor, QC are per-project/per-activity assignments**, resolved from the DB per request. The same employee can be Head in Project A, Lead in Project B, Contributor in Project C — with no change to their global role.

## 3. Confirmed decisions

1. Live data → every change additive with backfill + rollback + integrity checks.
2. **One Head per project**; Head absorbs the `project_managers` notification-routing role (that table is **deprecated in place**, deleted only after production verification).
3. Activities/sub-activities are the **existing `activity_master`** — no new activity table.
4. New **`project_activity_members`** join is the only new core table.
5. **Assignment is at the activity level** (`activity_master.level='activity'`); a report's `sub_activity_id` rolls up to its parent activity for the "is assigned?" check and for grouping.
6. **QC is a role** within an activity assignment (`role ∈ {lead, contributor, qc}`), not a separate activity or project-level role.
7. **Multiple Leads** and multiple Contributors per activity; QC optional.
8. `project_members` stays the **visibility backbone**, auto-maintained from assignments.
9. **PM never submits work reports.** QC submits their own reports like any employee and is **not** an approver.
10. **Report review = PM + Head only.** Activity Leads view their activity's reports but do not review.
11. Reports need **no schema change** (activity = parent of the existing `sub_activity_id`).

## 4. Data model

### 4.1 `project_activity_members` (new core table)
| column | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `project_id` | uuid FK→`projects` (CASCADE) | |
| `activity_id` | uuid FK→`activity_master` (RESTRICT) | must be a `level='activity'` node |
| `employee_id` | uuid FK→`employees` (RESTRICT) | |
| `role` | enum `lead \| contributor \| qc` | multiple leads allowed |
| `created_by` | uuid | |
| timestamps | | |

- **Unique** `(project_id, activity_id, employee_id)` — one role per person per activity per project.
- **No lead-uniqueness** constraint (one-or-more leads).
- Indexes: `(project_id)`, `(activity_id)`, `(employee_id)`, `(project_id, activity_id)`.
- A project "has" an activity when ≥1 assignment exists for it (no separate enablement table initially — YAGNI).
- Service-layer guard: reject `activity_id` whose `level != 'activity'`.

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
                          └─────────────── *:1─▶ employees   (role lead|contributor|qc)
projects ──1:*── project_members            (visibility backbone, auto-maintained)
work_report_tasks ─*:1─▶ activity_master(sub_activity) ─parent─▶ activity  (rollup)
project_deliverables ─*:1─▶ activity_master (optional activity_id)
```

## 5. Permissions — central helper (`app/core/authz.py`)

| Action | PM | Head (project) | Lead (activity) | Contributor | QC |
|---|---|---|---|---|---|
| Create/edit/archive projects, manage employees, approve leave | ✅ | ❌ | ❌ | ❌ | ❌ |
| Assign/replace Head | ✅ | ❌ | ❌ | ❌ | ❌ |
| Add activity to project; assign Leads/QC | ✅ | ✅ | ❌ | ❌ | ❌ |
| Assign/remove Contributors on an activity | ✅ | ✅ | ✅ (own activity) | ❌ | ❌ |
| Review reports (approve/reject/request-edit) | ✅ | ✅ | ❌ | ❌ | ❌ |
| Submit own reports (assigned activities) | ❌ never | ✅ | ✅ | ✅ | ✅ |
| View activity reports | all | all in project | own activity | own | own activity |
| View project / members / timeline | ✅ | ✅ | ✅ | ✅ | ✅ |

Helper API: `can_view_project`, `can_manage_project`, `can_manage_activity`, `can_assign_contributor(activity)`, `can_review_report`, `can_assign_head`. Ownership checks up the chain (PM ⊃ Head ⊃ Lead). Replaces the ~13 duplicated `_assert_can_*` helpers.

## 6. APIs (new/changed)
- `PUT /projects/{id}/head` — PM sets/replaces Head (+ timeline `HEAD_ASSIGNED/CHANGED`).
- `GET /projects/{id}/activities` — activities used by the project, each with Leads/Contributors/QC + counts.
- `POST /projects/{id}/activities/{activity_id}/members` `{employee_id, role}` — assign (Head/PM; Lead may add contributors to own activity).
- `PATCH /projects/{id}/activities/{activity_id}/members/{employee_id}` `{role}`.
- `DELETE /projects/{id}/activities/{activity_id}/members/{employee_id}`.
- `GET /projects/{id}/activities/{activity_id}/stats` — activity-wise counts/totals/pending/benchmark.
- `GET /me/activities` — caller's assigned activities across projects.
- Timeline events: `HEAD_ASSIGNED/CHANGED`, `ACTIVITY_MEMBER_ASSIGNED`, `ACTIVITY_MEMBER_REMOVED`.
- Submission gate (Phase 6): validate author assigned to the report line's activity.
- Project/activity responses return the caller's effective role (`my_project_role`, `my_activity_role`) for frontend gating.

## 7. Reporting flow, statistics & deliverables
- **Submit:** Contributor picks Project + Activity (assigned) + Sub-Activity + counts/minutes; backend derives activity = `parent(sub_activity)`; asserts assignment (enforced Phase 6); submit freezes benchmark snapshot (unchanged).
- **Stats (pure reads):** group `work_report_tasks` by parent activity → report counts, summed counts/minutes, benchmark comparison; per (project, activity, employee) and activity totals. No schema change.
- **Deliverables:** per-(project, activity) targets via `deliverables.activity_id`; completed = summed report counts; Head sees target/completed/remaining per activity ("which activity is behind?").
- **Review:** PM + Head across the project. **Export:** unchanged (already activity/sub-activity grouped).

## 8. Frontend
- Project detail → **Activities panel** (per activity: Leads/Contributors/QC + assign controls) → **Activity detail** (members, stats, reports, deliverables).
- **Head dashboard:** project → activities → per-activity staffing, report counts, completed counts, deliverable progress.
- **Activity Lead dashboard:** only their activities.
- **Contributor dashboard:** "My assigned activities" → sub-activities → submit.
- **Reports view:** grouped by activity → employee → totals.
- Gating from API effective roles; `rbac.ts` keeps PM/employee global gates only.

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
3. **Phase 3 — Assignment layer:** `project_activity_members` + assign/role/remove APIs (multiple leads; roles lead/contributor/qc) + auto-maintain visibility + timeline events.
4. **Phase 4 — Read models & dashboards:** activity-grouped reports, activity-wise stats, Head/Lead/Contributor dashboards.
5. **Phase 5 — Activity-wise deliverables:** `deliverables.activity_id` + target/completed/remaining.
6. **Phase 6 — Enforce submission gate + retire legacy** (`project_managers`, old `team_lead` role, `project_activities.assigned_to_id`) after production verification.

## 12. Future scalability
Assignments are a thin join; union scoping over `project_members` + `project_activity_members` is trivial at company scale (resolve a user's roles once per request). New master activities/sub-activities are instantly assignable — no migration. Optional `project_activity_targets`/enablement table slots in later for pre-staffing or period targets.

## 13. Out of scope (explicitly untouched)
The existing `project_activities` "Deliverable Activity Tracker" table/module/tab is unrelated to this model and is left as-is. `work_report_tasks`, benchmarks, employee-performance `tasks-tab` stay (naming collisions, part of the surviving reporting workflow).
