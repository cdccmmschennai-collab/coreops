/**
 * Pure-logic tests for the Report Detail "Overall task" badge.
 *
 * The bug this pins: a 2-work-day lump-sum activity started on the 22nd and
 * worked once read "Overdue by 2d", because the badge was derived from the
 * item's frozen CALENDAR due date. A lump-sum activity spends its allowed
 * duration in WORK DAYS, so on its first work day it is day 1 of 2 and not
 * overdue at all.
 *
 * Harness: `node --test` over src/**​/*.test.ts (see package.json test:unit) -
 * plain TypeScript, no jsdom / React Testing Library. The component delegates
 * the whole decision to overallTaskBadge, so the rule is fully pinned here. The
 * backend enforces the same rule independently (see backend
 * tests/test_lumpsum_workday_duration.py).
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { overallTaskBadge, type OverallTaskRow } from "./open-task-state.ts";

/** A saved lump-sum report row, `used` work days spent BEFORE this report. */
function lumpsumRow(used: number, target: number, lifecycle: string): OverallTaskRow {
  return {
    overall_lifecycle: lifecycle,
    overall_is_lumpsum: true,
    overall_target_days: target,
    overall_days_used: used,
    // Deliberately non-zero: the frozen calendar deadline has long passed and
    // must make no difference whatsoever to a lump-sum row.
    days_overdue: 7,
  };
}

// --------------------------------------------------------------------------
// lump-sum: measured in work days
// --------------------------------------------------------------------------
test("2-day lump-sum, first work day reads Day 1 of 2, not overdue", () => {
  const badge = overallTaskBadge(lumpsumRow(0, 2, "IN_PROGRESS"));
  assert.deepEqual(badge, { text: "Day 1 of 2", variant: "neutral" });
});

test("2-day lump-sum, second work day is still within the allowed duration", () => {
  // DUE_TODAY = the last allowed work day. In progress, nothing to approve.
  const badge = overallTaskBadge(lumpsumRow(1, 2, "DUE_TODAY"));
  assert.deepEqual(badge, { text: "Day 2 of 2", variant: "warning" });
});

test("2-day lump-sum, third work day reads Duration exceeded", () => {
  const badge = overallTaskBadge(lumpsumRow(2, 2, "OVERDUE"));
  assert.deepEqual(badge, { text: "Duration exceeded", variant: "danger" });
});

test("a stale calendar due date never leaks into a lump-sum badge", () => {
  // Every case above carries days_overdue = 7; none of them says "Overdue".
  for (const row of [
    lumpsumRow(0, 2, "IN_PROGRESS"),
    lumpsumRow(1, 2, "DUE_TODAY"),
    lumpsumRow(2, 2, "OVERDUE"),
  ]) {
    assert.ok(!overallTaskBadge(row)!.text.includes("Overdue"));
  }
});

test("a blank benchmark period still grants exactly one work day", () => {
  assert.equal(overallTaskBadge(lumpsumRow(0, 0, "DUE_TODAY"))!.text, "Day 1 of 1");
  assert.equal(
    overallTaskBadge(lumpsumRow(1, 0, "OVERDUE"))!.text,
    "Duration exceeded",
  );
});

// --------------------------------------------------------------------------
// everything else keeps the calendar lifecycle it has always had
// --------------------------------------------------------------------------
test("a non-lump-sum task keeps the calendar overdue badge", () => {
  const badge = overallTaskBadge({
    overall_lifecycle: "OVERDUE",
    overall_is_lumpsum: false,
    overall_target_days: 2,
    overall_days_used: null,
    days_overdue: 3,
  });
  assert.deepEqual(badge, { text: "Overdue by 3d", variant: "danger" });
});

test("a non-lump-sum task in progress keeps its calendar label", () => {
  const badge = overallTaskBadge({
    overall_lifecycle: "IN_PROGRESS",
    overall_is_lumpsum: false,
    days_overdue: 0,
  });
  assert.deepEqual(badge, { text: "In progress", variant: "neutral" });
});

test("completion stays a calendar verdict for a lump-sum item too", () => {
  // The server sends no work-day fields once the item is completed, so the row
  // falls through to the calendar branch by construction.
  const badge = overallTaskBadge({
    overall_lifecycle: "COMPLETED_LATE",
    overall_is_lumpsum: true,
    overall_target_days: 2,
    overall_days_used: null,
    days_overdue: 0,
  });
  assert.deepEqual(badge, { text: "Completed late", variant: "warning" });
});

test("an older backend that sends no work-day fields falls back to calendar", () => {
  const badge = overallTaskBadge({ overall_lifecycle: "OVERDUE", days_overdue: 2 });
  assert.deepEqual(badge, { text: "Overdue by 2d", variant: "danger" });
});

test("a legacy standalone row has no overall badge at all", () => {
  assert.equal(overallTaskBadge({ overall_lifecycle: null }), null);
  assert.equal(overallTaskBadge({}), null);
});
