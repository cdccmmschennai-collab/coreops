# Task 1 — Remove the assigned-task picker from the daily-report form

You are implementing **Task 1 of 7** in Phase 1 of CoreOps (removing a legacy "Task" module). This task is **frontend only**. After it, the backend still accepts a `task_id` field on report lines (it just ignores it), so this change is fully backward compatible.

## Goal
Remove the optional "link an assigned task" picker from the daily work report form, and stop sending `task_id` on each report line.

## Files to modify
- `frontend/src/features/work-reports/components/work-report-form.tsx`
- `frontend/src/features/work-reports/schemas.ts`

## Exact changes

1. In `work-report-form.tsx`, delete the import:
   `import { useTasks } from "@/features/tasks/hooks";` (around line 42).

2. In `work-report-form.tsx`, delete the task-picker data blocks: the `useTasks(...)` call and the `myTasksData` / `myTaskById` / `taskOptions` `useMemo`s (around lines 289–310). Then find and remove the JSX field that renders the task combobox (search the file for `taskOptions`, `myTaskById`, and any form field bound to a `...task_id` path — remove the field UI and any `form.setValue(...task_id...)` handlers tied only to it). Do NOT remove the Activity / Sub-Activity pickers — those stay.

3. In `schemas.ts`, remove the `task_id` field from the report-line schema (around line 145–146: `task_id: z.string().optional().default("")`), its default in the empty-line factory (around line 283: `task_id: ""`), and both mapper sites that read/write it (around line 356: `task_id: orNull(t.task_id)` and around line 421: `task_id: t.task_id ?? ""`). Ensure the object shapes still typecheck without `task_id`.

Line numbers are approximate — verify against the current file. Do NOT touch anything related to `work_report_tasks` completion, activity/sub-activity selection, benchmarks, or plants.

## Verification (run these; do not skip)
- `docker exec wms-frontend-1 npm run typecheck` → must PASS, with no remaining references to `task_id` or `useTasks` in the work-reports feature.
- `docker exec wms-frontend-1 npm run build` → must PASS.
- Grep to confirm: `grep -rn "task_id\|useTasks" frontend/src/features/work-reports` returns nothing.

## Hard constraints
- **Do NOT run any git command** (no add/commit/push). Leave changes in the working tree; a human commits later.
- Follow existing code style in the files you touch.
- Do not modify the implementation plan or any other files.

## Report contract
Write your full report to `/Users/sando/Desktop/coreops/.superpowers/sdd/task-1-report.md` containing: files changed with a short description each, the exact verification commands you ran and their output (typecheck, build, grep), and any concerns. Then return ONLY: your status (DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED), the list of files changed, a one-line test summary, and any concerns. Do not paste the full diff into your reply.
