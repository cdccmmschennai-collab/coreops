# Phase 1 — Remove Task Module — Progress Ledger

Plan: docs/superpowers/plans/2026-07-05-phase1-remove-task-module.md
Branch: head-role
BASE (pre-Phase-1 HEAD): fd94517
Execution: subagent-driven; git hands-off (user commits at each checkpoint).

## Tasks
- [x] Task 1: Remove assigned-task picker from report form (FE) — COMMITTED as 03e6c7a
- [x] Task 2: Re-source team-lead detection via GET /projects/led (BE+FE) — COMMITTED as 6f2b2ae
- [x] Task 3: Remove Task UI surface (FE) — implemented + verified; awaiting user commit
- [ ] Task 4: Sever backend seams (columns remain)
- [ ] Task 5: Remove backend Task module
- [ ] Task 6: Regenerate OpenAPI types
- [ ] Task 7: Drop Task DB objects (final, isolated migration)

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
