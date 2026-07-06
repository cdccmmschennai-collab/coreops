# Phase 2 — Head Ownership — Implementation Plan

> **For agentic workers:** implement task-by-task; each task ends at a **Checkpoint** where the *user* reviews and commits. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Introduce a per-project **Head** — one employee who owns a project and is its notification-routing target and (with the PM) a report reviewer — plus a central permission helper (`app/core/authz.py`). All additive: global roles stay `project_manager` + `employee`; Head is a per-project DB assignment resolved per request. No existing behavior is removed (the legacy `team_lead` reviewer path and `project_managers` routing table stay until Phase 6).

**Architecture:** New nullable `projects.head_employee_id`. A central `authz.py` resolves per-request project roles (PM ⊃ Head ⊃ member) from the DB, replacing scattered `_assert_can_*` checks incrementally (only where Head must be honored now). A PM-only `PUT /projects/{id}/head` assigns/replaces the Head, emits timeline events, and auto-maintains a `project_members` visibility row for the Head. Head is then honored in report review, project/timeline visibility, and notification routing (fallback: Head → `reporting_pm_id` → PM).

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (Postgres); Next.js + React Query + TS; Docker Compose (`wms-backend-1`, `wms-frontend-1`).

## Global Constraints

- **Git is hands-off for the agent.** Each task ends at a Checkpoint the *user* commits.
- **Backend tests:** `docker exec wms-backend-1 pytest` · in-container test path is `tests/...` (NOT `backend/tests/...`).
- **Frontend:** `docker exec wms-frontend-1 npm run typecheck` · `... npm run build`.
- **Every change additive, backward-compatible, independently deployable, rollback-safe.** No column/table dropped; `team_lead` review path and `project_managers` table remain (retired in Phase 6).
- **Migration numbering:** current head is `0052_day_status_half_day`. Phase 2's migration is **`0053_project_head`**. (The deferred Phase-1 Task 7 `drop_tasks` migration, when eventually written, chains *after* Phase 2's head migrations.)
- **Do NOT** change global JWT roles, remove `team_lead`, or touch `project_activities` (unrelated tracker). One Head per project (enforced by a single nullable column, not a join).
- **Test layout is flat:** `backend/tests/test_*.py` with fixtures `client`, `auth_header`, `make_project`, `make_user`, `make_employee`, `make_project_member`, `login` (confirm signatures against `conftest.py`).

---

### Task 1: Add `head_employee_id` (DB + model + read exposure)

Additive column; no behavior change. After this, a project can *carry* a Head but nothing assigns or reads it for logic yet.

**Files:**
- Create: `backend/alembic/versions/0053_project_head.py` (add nullable `head_employee_id` FK→employees `ON DELETE SET NULL` + index)
- Modify: `backend/app/modules/projects/models.py` (`Project.head_employee_id`)
- Modify: `backend/app/modules/projects/schemas.py` (`ProjectOut.head_employee_id`, `head_employee_name` populated by service join)
- Modify: `backend/app/modules/projects/service.py` (populate `head_employee_name` in the read decorators)

- [ ] Migration: `op.add_column("projects", sa.Column("head_employee_id", UUID, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True))` + `op.create_index`. `downgrade` drops index + column.
- [ ] Model: add `head_employee_id: Mapped[uuid.UUID | None]` (FK SET NULL, nullable).
- [ ] Schema: `head_employee_id: uuid.UUID | None = None`, `head_employee_name: str | None = None`.
- [ ] Service: resolve `head_employee_name` wherever `ProjectOut` is built (mirror existing `job_code_code` join pattern).
- [ ] Verify: `alembic upgrade head`; `pytest -q` (no new failures vs. the known pre-existing baseline); a `GET /projects/{id}` returns `head_employee_id: null`.
- [ ] **Checkpoint:** `feat(projects): add nullable head_employee_id column + read exposure (0053)`

---

### Task 2: Central `app/core/authz.py` helper (+ unit tests)

Pure, DB-resolving permission helpers. Additive — not yet wired into endpoints, so it cannot change behavior.

**Files:**
- Create: `backend/app/core/authz.py`
- Create: `backend/tests/test_authz.py`

**Interface (initial surface; grows in Phase 3):**
- `project_head_employee_id(db, project_id) -> UUID | None`
- `can_view_project(db, actor, project) -> bool` — PM, Head, or any `project_members` row.
- `can_manage_project(db, actor, project) -> bool` — PM only (create/edit/archive).
- `can_assign_head(db, actor, project) -> bool` — PM only.
- `can_review_report(db, actor, project_ids: set[UUID]) -> bool` — PM, **Head** of any of those projects, OR (legacy, until Phase 6) `team_lead` on any. Mirrors the current `_decorate` rule **plus Head**.

- [ ] Implement helpers resolving the caller's employee once, then checking PM role / Head column / membership. No writes.
- [ ] Unit tests: PM true everywhere; Head true for view/review on own project, false on others; contributor view-only; non-member false. Assert Head is honored by `can_review_report`.
- [ ] Verify: `pytest tests/test_authz.py -v` PASS.
- [ ] **Checkpoint:** `feat(authz): add central per-project permission helper with Head support`

---

### Task 3: `PUT /projects/{id}/head` — assign/replace Head (+ timeline + visibility)

**Files:**
- Modify: `backend/app/modules/projects/models.py` if a `TimelineEventType` enum needs `HEAD_ASSIGNED`/`HEAD_CHANGED` values (confirm how existing event types are defined).
- Modify: `backend/app/modules/projects/schemas.py` (`ProjectHeadUpdate { head_employee_id: UUID | None }`)
- Modify: `backend/app/modules/projects/service.py` (`set_project_head`: PM-guard via `authz.can_assign_head`; validate employee active; set column; emit `HEAD_ASSIGNED` (was null) or `HEAD_CHANGED`; **auto-add** the Head to `project_members` if absent; on replace, leave the prior member row (reference-counted cleanup is Phase 3))
- Modify: `backend/app/modules/projects/router.py` (`PUT /{project_id}/head`, PM-gated)
- Create: `backend/tests/test_project_head.py`

- [ ] Service validates the target employee exists + is active; setting `null` clears the Head (emits `HEAD_CHANGED`). Writes timeline event with `{head_employee_id, previous_head_employee_id}`.
- [ ] Route placed with the other `/{project_id}/...` routes; PM-gated (`require_role("project_manager")`).
- [ ] Tests: PM assigns Head → 200, column set, timeline row, Head appears in `project_members`; replace → `HEAD_CHANGED`; employee (non-PM) → 403; inactive employee → 422.
- [ ] Verify: `pytest tests/test_project_head.py -v` PASS; `pytest -q` no new failures.
- [ ] **Checkpoint:** `feat(projects): PUT /projects/{id}/head to assign/replace project Head + timeline`

---

### Task 4: Honor Head in review + visibility + notification routing

Wire the new authz into the surfaces that must respect Head **now**. Behavior change (additive permission): a Head gains review/visibility on their project; nothing is taken away.

**Files:**
- Modify: `backend/app/modules/work_reports/service.py` (`_decorate` `can_review` and `_assert_can_review` → include Head via `authz`, keeping the existing PM + team_lead paths)
- Modify: `backend/app/modules/projects/service.py` (`_assert_can_view_timeline` and project read scope → allow Head)
- Modify: notification routing for reports/activity-requests → target the Head first, falling back to `reporting_pm_id` → PM (locate the current routing helper; extend, don't replace)
- Modify/extend tests: `test_work_reports_*`, `test_project_head.py`

- [ ] Report review: Head of a report's project may reject / request-edit / grant-edit exactly as a PM can; `can_review` is `True` for the Head in the read model.
- [ ] Visibility: Head can `GET` the project + timeline even without a `team_lead` membership row.
- [ ] Routing: a report/activity-request notification goes to the project Head when set (else existing PM fallback). **R4:** Head vacancy falls back to `reporting_pm_id` → PM.
- [ ] Verify: new/updated tests PASS; `pytest -q` no new failures vs. baseline.
- [ ] **Checkpoint:** `feat: honor project Head in report review, project/timeline visibility, and notification routing`

---

### Task 5: Relax project timeline view to all project members

Spec §11 ("relax timeline view to members"). Any `project_members` row (not just `team_lead`) may view the timeline; PM + Head unchanged.

**Files:**
- Modify: `backend/app/modules/projects/service.py` (`_assert_can_view_timeline`)
- Modify: `backend/tests/test_projects.py` (or the timeline test file)

- [ ] `_assert_can_view_timeline`: allow PM, Head, and any project member.
- [ ] Test: a plain contributor member can view the timeline; a non-member 403s.
- [ ] Verify: `pytest -q` no new failures.
- [ ] **Checkpoint:** `feat(projects): relax timeline view to all project members`

---

### Task 6: Frontend — assign/show Head on project detail

**Files:**
- Modify: `frontend/openapi.json` + `frontend/src/types/openapi.ts` (regen after backend deploys Tasks 1+3 — `npm run gen:api`)
- Create/modify: a `useSetProjectHead` mutation hook + a Head panel in `frontend/src/features/projects/components/project-detail.tsx`
- Modify: project types to include `head_employee_id` / `head_employee_name`

- [ ] Project detail shows the current Head; PMs get an assign/replace control (employee picker scoped to project members or org employees per product call — confirm during build); employees see read-only.
- [ ] Gate the control on the caller being a PM (existing `isManagerial`/rbac).
- [ ] Verify: `npm run typecheck` PASS; `npm run build` PASS; manual — PM assigns a Head and sees it; timeline shows the event.
- [ ] **Checkpoint:** `feat(frontend): assign and display project Head on project detail`

---

## Self-Review

- **Additivity:** column nullable; `authz.py` purely new; `/head` PM-only; review/visibility widen (never narrow); routing extends the existing fallback. Every task independently deployable and rollback-safe (Task 1 migration has a real `downgrade`).
- **Ordering:** DB+model (1) → helper (2) → write API (3) → wire behavior (4) → relax view (5) → FE (6). Task 4 depends on 2+3; Task 6 regenerates types after 1+3 are deployed.
- **Backward-compat:** `team_lead` review and `project_managers` routing remain; Head is added alongside. Retirement is Phase 6.
- **Open product decisions to confirm during build:** (a) Head picker scope (project members vs. any employee); (b) whether assigning Head should also seed `project_managers` routing or fully supersede it in Phase 2 (spec deprecates it *in place* → keep both, prefer Head).
- **Out of scope (Phase 3+):** `project_activity_members`, activity roles (lead/contributor/qc), reference-counted visibility cleanup, `my_activity_role`.
