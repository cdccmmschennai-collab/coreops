# Phase 1 — Remove Task Module — Progress Ledger

Plan: docs/superpowers/plans/2026-07-05-phase1-remove-task-module.md
Branch: head-role
BASE (pre-Phase-1 HEAD): fd94517
Execution: subagent-driven; git hands-off (user commits at each checkpoint).

## Tasks
- [x] Task 1: Remove assigned-task picker from report form (FE) — review clean; awaiting user commit
- [ ] Task 2: Re-source team-lead detection via GET /projects/led (BE+FE)
- [ ] Task 3: Remove Task UI surface (FE)
- [ ] Task 4: Sever backend seams (columns remain)
- [ ] Task 5: Remove backend Task module
- [ ] Task 6: Regenerate OpenAPI types
- [ ] Task 7: Drop Task DB objects (final, isolated migration)

## Log
- Task 1: DONE. Files: work-report-form.tsx, schemas.ts. typecheck+build pass, grep clean. Reviewer: Spec ✅, Quality Approved, 0 findings. Extra line-removal (task_id from activity-request payload) verified necessary+backward-compatible. Awaiting user commit.
