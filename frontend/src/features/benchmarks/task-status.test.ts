/**
 * Pure-logic tests for the employee dashboard "Benchmark Activities" status.
 *
 * The bug this pins: a 2-work-day lump-sum activity started on 2026-08-21 and
 * worked once read "Overdue - 2 Days Overdue", because the card derived status
 * from the frozen CALENDAR due date. A lump-sum activity spends its allowance in
 * WORK DAYS, so with one work day used it is on day 2 of 2 and not overdue.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { benchmarkTaskState } from "./task-status.ts";
import type { TaskStatusRow } from "./types.ts";

const TODAY = new Date(2026, 7, 26); // 2026-08-26, local midnight

/** A dashboard task row. `used` = work days spent BEFORE today. */
function row(over: Partial<TaskStatusRow>): TaskStatusRow {
  return {
    work_report_task_id: "t1",
    activity_name: "Engineering",
    sub_activity_name: "FMTL Rework",
    project_name: null,
    project_code: "P1",
    report_date: "2026-08-21",
    due_date: "2026-08-24", // long past, and irrelevant for a lump-sum row
    completed_date: null,
    hours_minutes: 480,
    status: "pending",
    days_overdue: 0,
    ...over,
  };
}

function lumpsum(used: number, target: number): TaskStatusRow {
  return row({ is_lumpsum: true, days_used: used, target_days: target });
}

test("lump-sum on day 1 of 2 is In Progress, not overdue", () => {
  assert.deepEqual(benchmarkTaskState(lumpsum(0, 2), TODAY), {
    status: "in_progress",
    detail: "Day 1 of 2",
  });
});

test("lump-sum with one work day used is day 2 of 2 and still In Progress", () => {
  // The reported bug: due_date passed two days ago, but a work day remains.
  assert.deepEqual(benchmarkTaskState(lumpsum(1, 2), TODAY), {
    status: "in_progress",
    detail: "Day 2 of 2",
  });
});

test("lump-sum is Overdue only once the allowed work days are spent", () => {
  assert.deepEqual(benchmarkTaskState(lumpsum(2, 2), TODAY), {
    status: "overdue",
    detail: "Used 2 of 2 allowed work days",
  });
});

test("lump-sum worked beyond the allowance reports the days spent", () => {
  assert.deepEqual(benchmarkTaskState(lumpsum(4, 2), TODAY), {
    status: "overdue",
    detail: "Used 4 work days - 2 allowed",
  });
});

test("a blank benchmark period still grants one work day", () => {
  assert.equal(benchmarkTaskState(lumpsum(0, 0), TODAY).status, "in_progress");
  assert.equal(benchmarkTaskState(lumpsum(1, 0), TODAY).status, "overdue");
});

test("skipped calendar days never consume a lump-sum work day", () => {
  // Same item, a week later: nothing was worked in between, so days_used is
  // unchanged and the status must not drift with the calendar.
  const later = new Date(2026, 8, 2); // 2026-09-02
  assert.deepEqual(
    benchmarkTaskState(lumpsum(1, 2), later),
    benchmarkTaskState(lumpsum(1, 2), TODAY),
  );
});

test("non-lump-sum rows keep the calendar due-date wording", () => {
  assert.deepEqual(benchmarkTaskState(row({ due_date: "2026-08-28" }), TODAY), {
    status: "in_progress",
    detail: "Due in 2 Days",
  });
  assert.deepEqual(benchmarkTaskState(row({ due_date: "2026-08-27" }), TODAY), {
    status: "in_progress",
    detail: "Due in 1 Day",
  });
  assert.deepEqual(benchmarkTaskState(row({ due_date: "2026-08-26" }), TODAY), {
    status: "in_progress",
    detail: "Due Today",
  });
  assert.deepEqual(benchmarkTaskState(row({ due_date: "2026-08-25" }), TODAY), {
    status: "overdue",
    detail: "1 Day Overdue",
  });
  assert.deepEqual(benchmarkTaskState(row({ due_date: "2026-08-24" }), TODAY), {
    status: "overdue",
    detail: "2 Days Overdue",
  });
});

test("a row from an older backend (no lump-sum fields) stays on the calendar", () => {
  assert.equal(benchmarkTaskState(row({ due_date: "2026-08-24" }), TODAY).status, "overdue");
  // is_lumpsum true but no days_used (nothing to measure) also falls back.
  assert.equal(
    benchmarkTaskState(row({ is_lumpsum: true, due_date: "2026-08-24" }), TODAY).status,
    "overdue",
  );
});
