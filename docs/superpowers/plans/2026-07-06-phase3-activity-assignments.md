# Phase 3 — Activity Assignment Layer — Implementation Plan (revised model)

> **For agentic workers:** implement task-by-task; each task ends at a **Checkpoint** the *user* reviews and commits. Steps use checkbox (`- [ ]`) syntax.

**Precondition:** Phase 2 (Head ownership) deployed — `projects.head_employee_id`, `app/core/authz.py` (project-level helpers), `PUT /projects/{id}/head`, Head honored in review/visibility/routing.

**Goal:** Add the per-activity staffing layer that the **Head** manages: assign **exactly one Lead** per activity, **multiple Contributors**, and **QC as an additive flag** (`is_qc`) on any assigned member. Activity **Leads** manage Contributors + QC only within their own activity. **PM does not manage activity staffing.** The project detail page's flat members list is replaced by an **activity-grouped member view**.

**Model (from the revised architecture spec §4.1, §5, §6, §8):**
- `project_activity_members(project_id, activity_id, employee_id, role ∈ {lead, contributor}, is_qc bool, created_by, timestamps)`.
- Unique `(project_id, activity_id, employee_id)`; **partial-unique `(project_id, activity_id) WHERE role='lead'`** (≤1 Lead).
- `is_qc` may be `true` on a lead or a contributor; QC is never a standalone row.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (Postgres); Next.js + React Query + TS; Docker Compose.

## Global Constraints
- **Git hands-off for the agent**; each task ends at a user Checkpoint.
- Backend tests `docker exec wms-backend-1 pytest` (in-container path `tests/...`); FE `npm run typecheck` / `npm run build`.
- Every change additive, backward-compatible, independently deployable, rollback-safe. `project_members` stays the visibility backbone (auto-maintained here). `team_lead` role + `project_managers` remain until Phase 6.
- Migration numbering continues after Phase 2's `0053_project_head` (this phase: `0054_project_activity_members`).
- Reuse the `authz.py` central helper — no new scattered `_assert_can_*`.

---

### Task 1: `project_activity_members` table + model + schemas
Additive DB + ORM; no API yet.

**Files:** `backend/alembic/versions/0054_project_activity_members.py`; `backend/app/modules/projects/models.py` (new `ProjectActivityMember` + `ActivityMemberRole` enum); `backend/app/modules/projects/schemas.py` (`ActivityMemberOut`, `ActivityMemberCreate`, `ActivityMemberUpdate`, `ProjectActivityOut`).

- [ ] Migration: create table; `role` enum `project_activity_member_role {lead, contributor}`; `is_qc bool NOT NULL default false`; FKs (`project_id`→projects CASCADE, `activity_id`→activity_master RESTRICT, `employee_id`→employees RESTRICT); unique `(project_id, activity_id, employee_id)`; partial-unique index `... WHERE role='lead'`; indexes on `(project_id)`, `(activity_id)`, `(employee_id)`, `(project_id, activity_id)`. Real `downgrade`.
- [ ] Model + enum mirroring existing `ProjectMemberRole` style; schemas for read/create/update (`ActivityMemberCreate{employee_id, role, is_qc=false}`, `ActivityMemberUpdate{role?, is_qc?}`).
- [ ] Verify: `alembic upgrade head`; `import app.main`; `pytest -q` no new failures (vs. baseline).
- [ ] **Checkpoint:** `feat(projects): add project_activity_members table + model/schemas (0054)`

---

### Task 2: authz activity helpers (+ unit tests)
Extend `app/core/authz.py` (do not fork). Additive; wired by Task 3.

**Interface:** `activity_lead_employee_id(db, project_id, activity_id) -> UUID|None`; `can_manage_activity(db, actor, project) -> bool` (Head only — add activity / assign-replace Lead); `can_assign_contributor(db, actor, project_id, activity_id) -> bool` (Head, or the Lead of that activity — also gates QC toggling); `effective_activity_role(db, actor, project_id, activity_id) -> {"role": lead|contributor|None, "is_qc": bool}`.

- [ ] Implement; PM is **not** granted activity-staffing writes (view only). Unit tests: Head manages any activity; Lead manages only own; contributor/PM cannot; `effective_activity_role` returns correct role + `is_qc`.
- [ ] Verify: `pytest tests/test_authz.py -v` PASS.
- [ ] **Checkpoint:** `feat(authz): activity-staffing helpers (Head-manages, Lead-own-activity)`

---

### Task 3: Assignment APIs + service (one Lead, QC flag, auto-visibility)
**Files:** `backend/app/modules/projects/router.py` (activity routes), `service.py` (assignment service), `backend/tests/test_activity_members.py`.

Endpoints (spec §6): `GET /projects/{id}/activities`; `POST /projects/{id}/activities/{activity_id}/members {employee_id, role, is_qc?}`; `PATCH .../members/{employee_id} {role?, is_qc?}`; `DELETE .../members/{employee_id}`.

- [ ] Service rules: reject `activity_id` whose `activity_master.level != 'activity'`; `role='lead'` writes require `can_manage_activity` (Head) and replace the current Lead (DB partial-unique backstops a race); `role='contributor'` + any `is_qc` toggle require `can_assign_contributor` (Head or that activity's Lead); the **last Lead cannot be removed** while other members remain; **auto-maintain `project_members`** — every assignment ensures a `member` row, reference-counted removal on the person's last activity assignment on that project (unless they're Head or explicitly added). Centralize this in one function (spec R3).
- [ ] Timeline events `ACTIVITY_LEAD_ASSIGNED/CHANGED`, `ACTIVITY_MEMBER_ASSIGNED/REMOVED`, `ACTIVITY_QC_SET/CLEARED`.
- [ ] `GET /projects/{id}/activities` returns each activity with its Lead, Contributors, `is_qc` flags, counts, and the caller's `my_activity_role` + `my_is_qc`.
- [ ] Tests: Head assigns Lead → one-Lead enforced (2nd lead 422/409); Lead adds Contributor + toggles QC in own activity; Lead cannot touch another activity; PM cannot staff (403) but can GET; removing last Lead blocked; `project_members` row appears on assign and is cleaned up on last unassign.
- [ ] Verify: `pytest tests/test_activity_members.py -v` PASS; `pytest -q` no new failures.
- [ ] **Checkpoint:** `feat(projects): activity assignment APIs (Head/Lead, one-Lead, QC flag, auto-visibility)`

---

### Task 4: Frontend — activity-grouped member view (replaces flat members list)
**Files:** `frontend/openapi.json` + `src/types/openapi.ts` (regen after Task 3 deploys); new hooks (`useProjectActivities`, `useAssignActivityMember`, `useUpdateActivityMember`, `useRemoveActivityMember`); `frontend/src/features/projects/components/project-detail.tsx` (+ a new `activity-members` component); retire/replace the flat `project-members.tsx` usage on the detail page.

UI per spec §8 — three role views sharing a Head section + an activity-grouped member list (plain grouped text/badges, consistent with the existing project page):
- **Common list:** `Activities` → per activity: `Lead` (single) → `Contributors` (list) → `QC` (members with `is_qc`). A person may appear under both their base role and QC.
- **PM view:** Head section with Assign/Replace Head only; activities + members **read-only**; no staffing controls.
- **Head view:** one **single assignment form** (Employee dropdown = any employee · Activity dropdown = `activity_master` activities · Role = Lead|Contributor · QC checkbox · Add); assigning Lead replaces the existing Lead; on submit, only the **affected activity section** re-renders (targeted React Query invalidation, not full page).
- **Lead view:** own activity only; same form **without the Activity dropdown** (fixed to their activity); manages Contributors + QC there; cannot change the Lead.
- Employee picker is over **any** employee (confirmed decision).

- [ ] Build the Head section, the single assignment form, and the grouped member list; gate all controls on `my_project_role`/`my_activity_role` from the API; invalidate/refetch only the affected activity on mutation.
- [ ] Verify: `npm run gen:api`; `npm run typecheck` PASS; `npm run build` PASS; manual — Head adds an activity + Lead + Contributor + QC; Lead (as a different login) manages only their activity; PM sees read-only.
- [ ] **Checkpoint:** `feat(frontend): activity-grouped member view on project detail`

---

## Self-Review
- **Additivity/safety:** new table + new routes + new UI; nothing existing removed. `project_members` still the read backbone (now auto-maintained). Each task independently deployable; Task 1 migration has a real `downgrade`.
- **Ordering:** table (1) → authz (2) → API/service (3) → FE (4). Task 4 regenerates types after Task 3 is deployed.
- **Model fidelity to the revised workflow:** one Lead (partial-unique + service), QC additive (`is_qc`), Head manages all activities, Lead manages own-activity Contributors + QC, PM staffing-read-only.
- **Confirmed decisions honored:** any-employee picker; `project_members` auto-maintained; routing/`project_managers` untouched (Phase 6).
- **Deferred to Phase 4+:** `/me/activities`, Head/Lead/Contributor dashboards, activity-wise stats/deliverables, submission gate (Phase 6). Optional single-QC-per-activity constraint left as a future toggle.
