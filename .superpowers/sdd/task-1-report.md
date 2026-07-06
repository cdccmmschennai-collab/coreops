# Task 1 Report — Remove the assigned-task picker from the daily-report form

## Status: DONE

## Files changed

- `frontend/src/features/work-reports/components/work-report-form.tsx`
  - Removed `import { useTasks } from "@/features/tasks/hooks";`.
  - Removed the `myTasksData` (`useTasks(...)`), `myTaskById`, and `taskOptions` `useMemo`/data blocks that fed the task picker.
  - Removed the "Task (optional)" `FormField` bound to `tasks.${index}.task_id` (the Combobox that let a user link an assigned task and auto-fill the project/plant). The row's remove button, which shared a flex container with that field, was kept — the wrapper div now just holds the remove button (className changed from `flex items-end gap-2` to `flex items-end justify-end gap-2`, comment updated to "Row remove control.").
  - Removed `task_id: draft.task_id || null,` from the `createActivityRequest.mutateAsync(...)` payload inside `requestSecondActivity()` — `task_id` is an optional field on `ActivityRequestCreateBody` (`frontend/src/features/activity-requests/types.ts`), so omitting it is a no-op change, not a breaking one. This file wasn't in the brief's file list, so I only touched the call site inside `work-report-form.tsx`, not the type definition.
  - Activity / Sub-Activity pickers, benchmarks, plants, and `work_report_tasks` completion logic were left untouched.

- `frontend/src/features/work-reports/schemas.ts`
  - Removed `task_id: z.string().optional().default("")` from `taskSchema` (was directly above `task_title`, which is kept — it's still populated/read by `work-report-detail.tsx`, outside this task's scope).
  - Removed `task_id: ""` from `EMPTY_TASK_ROW`.
  - Removed `task_id: orNull(t.task_id),` from `toTasks()` (used by both `toCreateBody` and `toUpdateBody`).
  - Removed `task_id: t.task_id ?? "",` from `toFormValues()`'s tasks mapper.

## Verification

1. `grep -rn "task_id\|useTasks" frontend/src/features/work-reports`
   → No output (exit code 1 / no matches). Confirmed clean.

2. `docker exec wms-frontend-1 npm run typecheck`
   ```
   > wms-frontend@1.0.0 typecheck
   > tsc --noEmit
   ```
   → Passed with no errors.

3. `docker exec wms-frontend-1 npm run build`
   ```
   > wms-frontend@1.0.0 build
   > next build
    ✓ Compiled successfully
    Linting and checking validity of types ...
    Collecting page data ...
    ✓ Generating static pages (27/27)
    Finalizing page optimization ...
    Collecting build traces ...
   ```
   → Passed; all 27 routes built (including `/work-reports/new` and `/work-reports/[id]/edit`), no type or lint errors.

## Concerns

- The only touch outside the two named files' *content* was a payload key removed from a call in `work-report-form.tsx` itself (`task_id` in the `createActivityRequest.mutateAsync` call) — no other file was edited. This was necessary because that field is also in the `work-reports` feature directory and the brief's verification grep covers the whole `work-reports` tree. `task_id` remains defined (as optional) in `frontend/src/features/activity-requests/types.ts` and on the backend's `ActivityRequestCreateBody` handling — omitting it from the request body is backward compatible, matching this task's "frontend only, backward compatible" framing.
- `task_title` was intentionally left alone in both files (schema field, `EMPTY_TASK_ROW` default, and the `toFormValues` mapper) since it's rendered in `work-report-detail.tsx` (a file not in scope) and the brief only calls out `task_id` for removal.
- No git commands were run; all changes are left in the working tree for human review/commit.
