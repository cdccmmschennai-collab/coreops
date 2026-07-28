/**
 * Leave cancellation display rules (see types.ts).
 *
 * This repo has no DOM test runner by design, so these pin the pure rules the
 * leave history and the PM queue render from: which action a row offers, the
 * period shown in the confirmation dialog, the queue resolved from the URL, and
 * the attendance-summary labels. Rendering itself (the button element, the
 * absent reason field, the toast) stays manual.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  ATTENDANCE_SUMMARY_LABEL,
  LEAVE_QUEUES,
  LEAVE_STATUS_LABEL,
  attendanceSummaryLabel,
  businessToday,
  canCancelLeave,
  canRequestLeaveCancellation,
  formatLeavePeriod,
  resolveLeaveQueue,
} from "./types.ts";
import type { LeaveStatus } from "./types.ts";

const ME = "emp-1";
const TODAY = "2026-07-28";
const FUTURE = "2026-08-03";
const PAST = "2026-07-20";

const row = (status: LeaveStatus, end_date = FUTURE, employee_id = ME) => ({
  status,
  end_date,
  employee_id,
});

// ── 1. pending rows offer a direct cancel ───────────────────────────────────

test("an own pending request offers Cancel Request", () => {
  assert.equal(canCancelLeave(row("pending"), ME), true);
});

test("a pending request never offers Request Cancellation", () => {
  assert.equal(canRequestLeaveCancellation(row("pending"), ME, TODAY), false);
});

// ── 2./3./4. approved leave eligibility turns on end_date ───────────────────

test("approved future leave offers Request Cancellation", () => {
  assert.equal(canRequestLeaveCancellation(row("approved", FUTURE), ME, TODAY), true);
});

test("approved leave ending today is still eligible", () => {
  assert.equal(canRequestLeaveCancellation(row("approved", TODAY), ME, TODAY), true);
});

test("approved leave that started earlier but has not ended is eligible", () => {
  // The employee came back to work partway through the absence.
  const spanning = { status: "approved" as LeaveStatus, end_date: FUTURE, employee_id: ME };
  assert.equal(canRequestLeaveCancellation(spanning, ME, TODAY), true);
});

test("completely past approved leave is not eligible", () => {
  assert.equal(canRequestLeaveCancellation(row("approved", PAST), ME, TODAY), false);
});

test("approved leave never offers the direct pending cancel", () => {
  assert.equal(canCancelLeave(row("approved"), ME), false);
});

// ── 5. in-flight and terminal statuses offer nothing ────────────────────────

test("cancellation_requested offers no further action", () => {
  assert.equal(canCancelLeave(row("cancellation_requested"), ME), false);
  assert.equal(
    canRequestLeaveCancellation(row("cancellation_requested"), ME, TODAY),
    false,
  );
});

test("rejected and cancelled leave offer no action", () => {
  for (const status of ["rejected", "cancelled"] as LeaveStatus[]) {
    assert.equal(canCancelLeave(row(status), ME), false, status);
    assert.equal(canRequestLeaveCancellation(row(status), ME, TODAY), false, status);
  }
});

test("exactly one action is ever offered per row", () => {
  const statuses: LeaveStatus[] = [
    "pending",
    "approved",
    "rejected",
    "cancelled",
    "cancellation_requested",
  ];
  for (const status of statuses) {
    const both =
      canCancelLeave(row(status), ME) &&
      canRequestLeaveCancellation(row(status), ME, TODAY);
    assert.equal(both, false, status);
  }
});

// ── ownership ───────────────────────────────────────────────────────────────

test("another employee's rows offer nothing", () => {
  assert.equal(canCancelLeave(row("pending", FUTURE, "emp-2"), ME), false);
  assert.equal(
    canRequestLeaveCancellation(row("approved", FUTURE, "emp-2"), ME, TODAY),
    false,
  );
});

test("an account with no linked employee is never treated as the owner", () => {
  assert.equal(canCancelLeave(row("pending"), null), false);
  assert.equal(canRequestLeaveCancellation(row("approved"), undefined, TODAY), false);
});

// ── business-day boundary ───────────────────────────────────────────────────

test("today is taken from the Chennai business day, not UTC", () => {
  // 2026-07-27T20:00Z is already 2026-07-28 in Asia/Kolkata (+05:30).
  const lateEvening = new Date("2026-07-27T20:00:00Z");
  assert.equal(businessToday(lateEvening), "2026-07-28");
  assert.equal(businessToday(lateEvening, "UTC"), "2026-07-27");
});

test("leave that ended on the IST day is not reopened by a stale UTC date", () => {
  const today = businessToday(new Date("2026-07-27T20:00:00Z")); // 2026-07-28
  assert.equal(canRequestLeaveCancellation(row("approved", "2026-07-27"), ME, today), false);
});

// ── 6. the period shown in the confirmation dialog ──────────────────────────

test("a single-day period renders one date", () => {
  assert.equal(formatLeavePeriod("2026-08-03", "2026-08-03"), "3 August 2026");
});

test("a multi-day period renders both dates", () => {
  assert.equal(
    formatLeavePeriod("2026-07-28", "2026-07-30"),
    "28 July 2026 - 30 July 2026",
  );
});

test("a period is built from local date parts, not a UTC parse", () => {
  assert.equal(formatLeavePeriod("2026-01-01", "2026-01-01"), "1 January 2026");
});

// ── 12./13. PM queue resolution from the URL ────────────────────────────────

test("the URL selects the cancellation queue", () => {
  assert.equal(resolveLeaveQueue("cancellation"), "cancellation");
});

test("every known queue round-trips", () => {
  for (const q of LEAVE_QUEUES) assert.equal(resolveLeaveQueue(q), q);
});

test("a missing or invalid queue falls back to pending", () => {
  assert.equal(resolveLeaveQueue(null), "pending");
  assert.equal(resolveLeaveQueue(undefined), "pending");
  assert.equal(resolveLeaveQueue(""), "pending");
  assert.equal(resolveLeaveQueue("nonsense"), "pending");
  // an existing /attendance?tab=leave link carries no queue at all
  assert.equal(resolveLeaveQueue(new URLSearchParams("tab=leave").get("queue")), "pending");
});

// ── 11. attendance summary labels ───────────────────────────────────────────

test("attendance summary codes map to the agreed labels", () => {
  assert.equal(attendanceSummaryLabel("present"), "Present recorded");
  assert.equal(attendanceSummaryLabel("leave"), "Leave recorded");
  assert.equal(attendanceSummaryLabel("absent"), "Absent recorded");
  assert.equal(attendanceSummaryLabel("mixed"), "Multiple statuses");
  assert.equal(attendanceSummaryLabel("none"), "No attendance");
});

test("a missing summary reads as No attendance rather than blank", () => {
  assert.equal(attendanceSummaryLabel(undefined), ATTENDANCE_SUMMARY_LABEL.none);
});

test("an unknown status code degrades to a generic label", () => {
  assert.equal(attendanceSummaryLabel("something_new"), "Attendance recorded");
});

// ── status labels ───────────────────────────────────────────────────────────

test("every status has a user-friendly label", () => {
  assert.deepEqual(LEAVE_STATUS_LABEL, {
    pending: "Pending",
    approved: "Approved",
    rejected: "Rejected",
    cancelled: "Cancelled",
    cancellation_requested: "Cancellation Requested",
  });
});
