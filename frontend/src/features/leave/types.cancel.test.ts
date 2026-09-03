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
  LEAVE_LIST_HREF,
  LEAVE_QUEUES,
  LEAVE_STATUS_LABEL,
  attendanceSummaryLabel,
  businessToday,
  canCancelLeave,
  canRequestLeaveCancellation,
  formatLeavePeriod,
  leaveDetailHref,
  leaveReturnHref,
  resolveLeaveQueue,
  resolveLeaveView,
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


// ── a Head's My leave / Team approvals switch, and browser Back ─────────────

test("an explicit ?view always wins, so Back restores what was open", () => {
  // Both choices are written into the URL, which is the whole point: Back
  // reads them straight back instead of inferring anything.
  assert.equal(resolveLeaveView("team", false), "team");
  assert.equal(resolveLeaveView("my", true), "my");
  assert.equal(resolveLeaveView("team", true), "team");
  assert.equal(resolveLeaveView("my", false), "my");
});

test("a link that names only a queue still opens Team approvals", () => {
  // The dashboard shortcut and the backend leave notifications predate ?view
  // and carry ?tab=leave&queue=pending&id=... - a queue is a Team approvals
  // queue, so those keep working.
  const legacy = new URLSearchParams("tab=leave&queue=pending&id=abc");
  assert.equal(
    resolveLeaveView(legacy.get("view"), legacy.get("queue") !== null),
    "team",
  );
});

test("with neither parameter a Head lands on their own leave", () => {
  const bare = new URLSearchParams("tab=leave");
  assert.equal(
    resolveLeaveView(bare.get("view"), bare.get("queue") !== null),
    "my",
  );
  // A hand-edited or stale value is not a third view.
  assert.equal(resolveLeaveView("banana", false), "my");
  assert.equal(resolveLeaveView("", false), "my");
  assert.equal(resolveLeaveView(undefined, false), "my");
});


// ── Leave list -> detail -> "← Leave Requests" back to the SAME list ─────────────────

test("a detail link carries the list it was opened from", () => {
  assert.equal(
    leaveDetailHref("req-1", "/attendance?tab=leave&view=team&queue=pending"),
    "/attendance/leave/req-1?from=%2Fattendance%3Ftab%3Dleave%26view%3Dteam%26queue%3Dpending",
  );
});

test("with nothing to return to the detail URL is unchanged", () => {
  assert.equal(leaveDetailHref("req-1"), "/attendance/leave/req-1");
  assert.equal(leaveDetailHref("req-1", null), "/attendance/leave/req-1");
  assert.equal(leaveDetailHref("req-1", "   "), "/attendance/leave/req-1");
});

test("the detail link round-trips through the URL it was built from", () => {
  // Team approvals -> Pending: the queue and the view both survive.
  const list = "/attendance?tab=leave&view=team&queue=pending";
  const href = leaveDetailHref("req-1", list);
  const from = new URLSearchParams(href.split("?")[1]).get("from");
  assert.equal(leaveReturnHref(from), list);
});

test("every Leave list comes back to itself, with no case per queue", () => {
  for (const list of [
    "/attendance?tab=leave",
    "/attendance?tab=leave&view=my",
    "/attendance?tab=leave&view=team&queue=pending",
    "/attendance?tab=leave&view=team&queue=cancellation",
    "/attendance?tab=leave&queue=permission",
    "/attendance?tab=leave&view=team&queue=all&ls=approved&lo=20",
  ]) {
    const href = leaveDetailHref("req-1", list);
    const from = new URLSearchParams(href.split("?")[1]).get("from");
    assert.equal(leaveReturnHref(from), list, list);
  }
});

test("a deep-linked detail page still falls back to the Leave tab", () => {
  // An email link or a bookmark carries no `from` at all - unchanged behaviour.
  assert.equal(leaveReturnHref(null), LEAVE_LIST_HREF);
  assert.equal(leaveReturnHref(undefined), LEAVE_LIST_HREF);
  assert.equal(leaveReturnHref(""), LEAVE_LIST_HREF);
});

test("a from that is not the Attendance page is never followed", () => {
  // `from` is written by the app for itself; a forwarded or hand-edited URL
  // does not get to choose where this link goes.
  for (const hostile of [
    "https://evil.example/attendance",
    "//evil.example/attendance",
    "/attendance-x?tab=leave",
    "/projects?tab=leave",
    "javascript:alert(1)",
    "/login?next=/attendance",
  ]) {
    assert.equal(leaveReturnHref(hostile), LEAVE_LIST_HREF, hostile);
  }
});
