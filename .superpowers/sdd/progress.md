# Phase 1 — Remove Task Module — Progress Ledger

Plan: docs/superpowers/plans/2026-07-05-phase1-remove-task-module.md
Branch: head-role
BASE (pre-Phase-1 HEAD): fd94517
Execution: subagent-driven; git hands-off (user commits at each checkpoint).

## Tasks
- [x] Task 1: Remove assigned-task picker from report form (FE) — COMMITTED as 03e6c7a
- [x] Task 2: Re-source team-lead detection via GET /projects/led (BE+FE) — implemented + verified; awaiting user commit
- [ ] Task 3: Remove Task UI surface (FE)
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
