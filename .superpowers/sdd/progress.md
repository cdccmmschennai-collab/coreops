# Phase 1 — Remove Task Module — Progress Ledger

Plan: docs/superpowers/plans/2026-07-05-phase1-remove-task-module.md
Branch: head-role
BASE (pre-Phase-1 HEAD): fd94517
Execution: subagent-driven; git hands-off (user commits at each checkpoint).

## Tasks
- [x] Task 1: Remove assigned-task picker from report form (FE) — COMMITTED as 03e6c7a
- [x] Task 2: Re-source team-lead detection via GET /projects/led (BE+FE) — COMMITTED as 6f2b2ae
- [x] Task 3: Remove Task UI surface (FE) — COMMITTED as a478faa
- [x] Task 4: Sever backend seams (columns remain) — implemented + verified; awaiting user commit
- [x] Task 5: Remove backend Task module — implemented + verified; awaiting user commit
- [x] Task 6: Regenerate OpenAPI types — implemented + verified; awaiting user commit
- [ ] Task 7: Drop Task DB objects (final, isolated migration) — IRREVERSIBLE, needs DB backup; STOPPED for user confirm

## Log
- Task 1: DONE + COMMITTED as 03e6c7a (verified: no task_id/useTasks in features/work-reports; HEAD = BASE fd94517 + this commit). Ledger "awaiting commit" was stale from the other machine.
- Task 2: DONE (awaiting user commit). Files: BE projects/schemas.py (LedProject/LedProjectMember), projects/service.py (list_led_projects), projects/router.py (GET /projects/led before /{project_id}); tests/test_led_projects.py (2 tests). FE features/projects/hooks/use-led-projects.ts (new), work-reports/components/work-reports-view.tsx (switched useAssignableProjects→useLedProjects).
  - Verification: new test 2/2 PASS; projects suite 23 + led 2 = 25 PASS; FE typecheck PASS; FE build PASS.
  - Deviations from plan (both explained + safe): (1) test adapted to real fixtures (make_employee needs employee_code + user_id=; make_project_member fixture used; login takes email string) — plan Step 1 explicitly directed this. (2) In-container pytest path is tests/... not backend/tests/... (plan paths are host-relative). (3) Hoisted LedProject/LedProjectMember into service.py's existing top-level schemas import (no circular dep) instead of inline import + string annotation, to clear a basedpyright forward-ref warning.
  - Intentional behavior note: /projects/led INCLUDES the lead + drops the user_id filter (reports-scope filter), unlike the retired /tasks/assignable-projects which excluded the lead. Matches plan's given service code + test. View dedupes via `seen` map so no double-count.
- Task 3: DONE (awaiting user commit). Deleted FE app/(app)/tasks/ (5 pages) + features/tasks/ (11 files). Modified: components/shell/sidebar.tsx (removed Tasks nav item + ListTodo import), features/dashboard/project-manager-dashboard.tsx (removed "Assign task" link + ListChecks import), lib/rbac.ts (removed task.view + task.manage from Capability union + MATRIX).
  - Verification: Step-1 grep clean (no external features/tasks importers; only survivors are openapi.ts /tasks paths→Task 6, and KEEP look-alikes: work-reports/tasks completion + employee-performance TasksTab). FE build PASS (route list now has zero /tasks routes). FE typecheck PASS.
  - Deviation: typecheck initially failed on STALE .next/types/app/(app)/tasks/page.ts (Next.js generated route types for the deleted page). Ran build first to regenerate .next/types, then typecheck passed. Artifact staleness only — no source issue. (Plan lists typecheck before build; ran build first to clear stale generated types.)
  - Manual check remaining (user): sidebar has no Tasks item, PM dashboard has no "Assign task", /tasks 404s, Reports/Projects unaffected.
- Task 4: DONE (awaiting user commit). Stopped reading/writing Task links; DB columns untouched (dropped later in Task 7).
  - BE work_reports/service.py: removed `from app.modules.tasks.models import Task`; removed linked-Task title-resolution block; removed `"task_title"` from snapshot dict; removed `task_id=`/`task_title=` from BOTH WorkReportTask constructions (create + update paths — 2nd had 20-space indent, needed a separate edit).
  - BE work_reports/schemas.py: removed task_id from WorkReportTaskIn; removed task_id + task_title from WorkReportTaskOut.
  - BE activity_requests/service.py: removed Task import; removed task_ids set + tasks bulk-fetch + task lookup in _attach_names (task_title now hard-set None for API back-compat); removed task_id= in create_request; removed task_id from SimpleNamespace + task_id=/task_title= from WorkReportTask in _create_task_from_request.
  - BE activity_requests/schemas.py: removed task_id from ActivityRequestCreate + ActivityRequestOut. KEPT task_title output field (defaults None) — plan scoped schema change to task_id only; back-compat.
  - Verification: `python -c import app.main` OK. activity_requests suite FULLY PASSES. 12 full-suite failures are ALL PRE-EXISTING (proven: `git stash` → same 11 fail at HEAD a478faa; 12th = test_report_approved_notifies_author posts to removed /approve endpoint). None caused by Task 4. Working tree restored after stash.
  - Pre-existing failures are the removed-approval-flow family (svc.approve_work_report / POST .../approve / list-scope) + 1 date-flaky benchmark overdue test (today=Mon 2026-07-06 makes due_date-2=Sat fall before week_start).
  - Deviation: activity_requests task_title set to explicit None (not removed) — model has no task_title column, schema keeps field for back-compat, plan says "set to None/omit".
  - Out-of-scope note: work_reports/service.py `_team_ids` (line 231) is pre-existing dead code (unused); left untouched per Task-4 scope.
  - NOT run: FE typecheck/build (Task 4 is backend-only; frontend stopped sending task_id in Task 1).
- Task 5: DONE (awaiting user commit). Deleted backend/app/modules/tasks/ (5 files) + backend/tests/test_tasks.py. Removed tasks_router import + include_router from main.py. Audit constants kept.
  - TWO UNPLANNED-BUT-REQUIRED FIXES (plan's Task 5 file list was incomplete; adapted to repo, back-compat preserved):
    (1) alembic/env.py: removed `import app.modules.tasks.models` (model registration) — otherwise ModuleNotFoundError broke ALL migrations/tests.
    (2) work_reports/models.py + activity_requests/models.py: removed `ForeignKey("tasks.id", ondelete="SET NULL")` from the surviving task_id columns (kept the columns as plain nullable UUID). After deleting the Task model, the tasks Table left SQLAlchemy metadata, so these FKs raised NoReferencedTableError on every insert. DB columns + DB FK constraints untouched (dropped in Task 7); only the ORM FK *declaration* removed.
  - Verification: `import app.main` OK. Full suite: SAME 12 pre-existing failures, ZERO new failures, ZERO collection errors after deleting test_tasks.py. Guardrail benchmark_alerts fully green; benchmark_engine green except the 1 date-flaky overdue test; activity_requests fully green.
- Task 6: DONE (awaiting user commit). Regenerated frontend/openapi.json (from backend app.openapi(), UTF-8 no BOM; no /api/v1/tasks paths; work-report completion endpoint retained) + src/types/openapi.ts via `npm run gen:api`.
  - Export mechanism deviation: plan's in-container write path /app/../frontend won't work (backend container mounts only backend/ at /app). Instead dumped app.openapi() to stdout and wrote host frontend/openapi.json via PowerShell [System.IO.File]::WriteAllText UTF-8-no-BOM.
  - UNPLANNED-BUT-REQUIRED FE fixes (regenerated types dropped work_report_tasks.task_title, exposing read-side consumers the plan didn't enumerate; typecheck failed until fixed): removed task_title read in work-reports/schemas.ts edit-mapper (line ~417); removed the "Linked task" display block in work-report-detail.tsx; removed t.task_title fallback in employee-performance tasks-tab.tsx title expr. All minimal.
  - KEPT (correct, back-compat): ActivityRequestOut.task_title in openapi.ts + activity-requests/types.ts (backend still returns it, now always null); work-reports form's own optional task_title zod field + default (harmless leftover, not payload-mapped).
  - Verification: gen:api OK; FE typecheck PASS; FE build PASS (no /tasks routes).
