/**
 * Permission display rules (see types.ts).
 *
 * This repo has no DOM test runner by design, so these pin the pure rules the
 * dialog and the history table render from: the live balance preview, which
 * durations are offered, and which rows offer Cancel. The rules that MATTER -
 * whether an approval is allowed at all - are enforced and tested in the backend
 * (`tests/test_permissions_phase11.py`); nothing here is a check.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  MONTHLY_ALLOWANCE_HOURS,
  PERMISSION_DURATIONS,
  PERMISSION_HISTORY_PATH,
  permissionDetailPath,
  PERMISSION_DURATION_LABEL,
  PERMISSION_PERIOD_HOURS,
  PERMISSION_PERIOD_LABEL,
  PERMISSION_PERIOD_OPTIONS,
  PERMISSION_STATUS_LABEL,
  businessToday,
  canCancelPermission,
  canReviewPermission,
  currentBusinessMonth,
  formatAvailable,
  formatDuration,
  formatHours,
  formatMonthLabel,
  formatPermissionDuration,
  formatShortDate,
  isDurationAffordable,
  monthStart,
  remainingAfter,
  shiftMonth,
} from "./types.ts";
import type { PermissionStatus } from "./types.ts";

const ME = "emp-1";
const TODAY = "2026-08-17";
const FUTURE = "2026-08-20";
const PAST = "2026-08-10";

const row = (status: PermissionStatus, permission_date = FUTURE, employee_id = ME) => ({
  status,
  permission_date,
  employee_id,
});

// ── only 1h and 2h exist ────────────────────────────────────────────────────

test("exactly two durations are offered, and neither is a half hour", () => {
  assert.deepEqual([...PERMISSION_DURATIONS], [1, 2]);
  assert.deepEqual(PERMISSION_DURATION_LABEL, { 1: "1 hour", 2: "2 hours" });
});

test("the monthly allowance is four hours", () => {
  assert.equal(MONTHLY_ALLOWANCE_HOURS, 4);
});

// ── the live balance preview ─────────────────────────────────────────────────

test("1h against a full month previews 3h remaining", () => {
  assert.equal(remainingAfter(4, 1), 3);
});

test("2h against a full month previews 2h remaining", () => {
  assert.equal(remainingAfter(4, 2), 2);
});

test("the worked example walks 4h to 0h", () => {
  let remaining = MONTHLY_ALLOWANCE_HOURS;
  remaining = remainingAfter(remaining, 1);
  assert.equal(remaining, 3);
  remaining = remainingAfter(remaining, 2);
  assert.equal(remaining, 1);
  remaining = remainingAfter(remaining, 1);
  assert.equal(remaining, 0);
});

test("an over-large selection previews 0h, never a negative figure", () => {
  assert.equal(remainingAfter(1, 2), 0);
  assert.equal(remainingAfter(0, 1), 0);
});

// ── which durations the dropdown offers ─────────────────────────────────────

test("with 1h remaining, 1h is offered and 2h is not", () => {
  assert.equal(isDurationAffordable(1, 1), true);
  assert.equal(isDurationAffordable(2, 1), false);
});

test("with a full month both durations are offered", () => {
  for (const hours of PERMISSION_DURATIONS) {
    assert.equal(isDurationAffordable(hours, 4), true, String(hours));
  }
});

test("with 0h remaining nothing is affordable", () => {
  for (const hours of PERMISSION_DURATIONS) {
    assert.equal(isDurationAffordable(hours, 0), false, String(hours));
  }
});

// ── formatting ──────────────────────────────────────────────────────────────

test("hours render as the KPI shows them", () => {
  assert.equal(formatHours(4), "4h");
  assert.equal(formatHours(0), "0h");
});

test("a duration renders compactly beside a status", () => {
  assert.equal(formatDuration(1), "1hr");
  assert.equal(formatDuration(2), "2hr");
});

// ── the four Phase 4C period options ────────────────────────────────────────

test("exactly four period options exist, and there is no plain 1 Hour / 2 Hours", () => {
  assert.deepEqual(
    [...PERMISSION_PERIOD_OPTIONS],
    ["first_half_1h", "second_half_1h", "first_half_2h", "second_half_2h"],
  );
  assert.deepEqual(PERMISSION_PERIOD_LABEL, {
    first_half_1h: "1st Half — 1 Hour",
    second_half_1h: "2nd Half — 1 Hour",
    first_half_2h: "1st Half — 2 Hours",
    second_half_2h: "2nd Half — 2 Hours",
  });
});

test("each period option costs the hours its label states", () => {
  assert.deepEqual(PERMISSION_PERIOD_HOURS, {
    first_half_1h: 1,
    second_half_1h: 1,
    first_half_2h: 2,
    second_half_2h: 2,
  });
});

test("a request with a period shows the actual selected option, never the plain hour count", () => {
  assert.equal(
    formatPermissionDuration({ period: "first_half_1h", duration_hours: 1 }),
    "1st Half — 1 Hour",
  );
  assert.equal(
    formatPermissionDuration({ period: "second_half_2h", duration_hours: 2 }),
    "2nd Half — 2 Hours",
  );
});

test("a pre-Phase-4C request with no period falls back to the plain compact form", () => {
  assert.equal(formatPermissionDuration({ period: null, duration_hours: 1 }), "1hr");
  assert.equal(formatPermissionDuration({ period: null, duration_hours: 2 }), "2hr");
});

// ── which rows offer Cancel ─────────────────────────────────────────────────

test("an own pending request can be cancelled whatever its date", () => {
  assert.equal(canCancelPermission(row("pending", PAST), ME, TODAY), true);
  assert.equal(canCancelPermission(row("pending", FUTURE), ME, TODAY), true);
});

test("an own approved request can be cancelled up to and including its day", () => {
  assert.equal(canCancelPermission(row("approved", FUTURE), ME, TODAY), true);
  assert.equal(canCancelPermission(row("approved", TODAY), ME, TODAY), true);
  assert.equal(canCancelPermission(row("approved", PAST), ME, TODAY), false);
});

test("terminal statuses offer nothing", () => {
  for (const status of ["rejected", "cancelled"] as PermissionStatus[]) {
    assert.equal(canCancelPermission(row(status), ME, TODAY), false, status);
  }
});

test("another employee's rows offer nothing, and neither do unlinked accounts", () => {
  assert.equal(canCancelPermission(row("pending", FUTURE, "emp-2"), ME, TODAY), false);
  assert.equal(canCancelPermission(row("pending"), null, TODAY), false);
  assert.equal(canCancelPermission(row("approved"), undefined, TODAY), false);
});

// ── business-day boundary ───────────────────────────────────────────────────

test("today is taken from the Chennai business day, not UTC", () => {
  // 2026-08-16T20:00Z is already 2026-08-17 in Asia/Kolkata (+05:30).
  const lateEvening = new Date("2026-08-16T20:00:00Z");
  assert.equal(businessToday(lateEvening), "2026-08-17");
  assert.equal(businessToday(lateEvening, "UTC"), "2026-08-16");
});

test("a permission whose IST day has passed is not reopened by a stale UTC date", () => {
  const today = businessToday(new Date("2026-08-16T20:00:00Z")); // 2026-08-17
  assert.equal(canCancelPermission(row("approved", "2026-08-16"), ME, today), false);
});

// ── status labels ───────────────────────────────────────────────────────────

test("every status has a user-friendly label and there is no fifth one", () => {
  assert.deepEqual(PERMISSION_STATUS_LABEL, {
    pending: "Pending",
    approved: "Approved",
    rejected: "Rejected",
    cancelled: "Cancelled",
  });
});

// ══ Phase 11A ═══════════════════════════════════════════════════════════════
//
// The month value carried in the URL is `YYYY-MM-DD` on the 1st, which is exactly
// what the API's `month` parameter takes, so these also pin the wire format.

// ── routes ──────────────────────────────────────────────────────────────────

test("the History action carries no month, so it always opens the current one", () => {
  // The page defaults `pm_month` to the current month and useUrlState strips it
  // from the URL when it matches, so a bare path IS the current month. A month
  // baked in here would pin History to whatever month was hard-coded.
  assert.equal(PERMISSION_HISTORY_PATH, "/attendance/permission");
  assert.equal(PERMISSION_HISTORY_PATH.includes("?"), false);
});

test("a detail path hangs off the history path", () => {
  assert.equal(permissionDetailPath("abc-123"), "/attendance/permission/abc-123");
  assert.ok(permissionDetailPath("abc-123").startsWith(PERMISSION_HISTORY_PATH));
});

// ── month navigation ────────────────────────────────────────────────────────

test("any date in a month resolves to that month's first day", () => {
  assert.equal(monthStart("2026-08-17"), "2026-08-01");
  assert.equal(monthStart("2026-08-01"), "2026-08-01");
  assert.equal(monthStart("2026-08-31"), "2026-08-01");
  // A bare YYYY-MM is accepted too, so a hand-edited URL still resolves.
  assert.equal(monthStart("2026-08"), "2026-08-01");
});

test("a nonsense month falls back to the current business month, never NaN", () => {
  assert.equal(monthStart("nonsense"), currentBusinessMonth());
  assert.equal(monthStart(""), currentBusinessMonth());
});

test("stepping back and forward returns to the same month", () => {
  assert.equal(shiftMonth("2026-08-01", -1), "2026-07-01");
  assert.equal(shiftMonth("2026-08-01", 1), "2026-09-01");
  assert.equal(shiftMonth(shiftMonth("2026-08-01", -1), 1), "2026-08-01");
});

test("stepping across a year boundary rolls the year", () => {
  assert.equal(shiftMonth("2026-01-01", -1), "2025-12-01");
  assert.equal(shiftMonth("2026-12-01", 1), "2027-01-01");
  // 14 months back from March 2027 is January 2026.
  assert.equal(shiftMonth("2027-03-01", -14), "2026-01-01");
});

test("stepping is computed from the month, not the day, so no month is skipped", () => {
  // 31 Jan + 1 month must be February, not March - which naive Date arithmetic
  // would produce by overflowing the 31st.
  assert.equal(shiftMonth("2026-01-31", 1), "2026-02-01");
  assert.equal(shiftMonth("2026-03-31", -1), "2026-02-01");
});

test("the current business month comes from the Chennai day, not UTC", () => {
  // 2026-07-31T20:00Z is already 2026-08-01 in Asia/Kolkata (+05:30), so a
  // UTC-based month would still say July.
  assert.equal(currentBusinessMonth(new Date("2026-07-31T20:00:00Z")), "2026-08-01");
});

// ── month + date formatting ─────────────────────────────────────────────────

test("a month renders as the history heading", () => {
  assert.equal(formatMonthLabel("2026-08-01"), "August 2026");
  assert.equal(formatMonthLabel("2027-01-01"), "January 2027");
  assert.equal(formatMonthLabel("2027-12-01"), "December 2027");
});

test("a date renders as the history row shows it", () => {
  assert.equal(formatShortDate("2026-08-17"), "17 Aug 2026");
  assert.equal(formatShortDate("2026-08-05"), "05 Aug 2026");
  assert.equal(formatShortDate("2026-01-01"), "01 Jan 2026");
});

test("a date is formatted from its parts, so it never shifts across UTC", () => {
  // A UTC parse of "2026-01-01" renders as 31 Dec 2025 west of Greenwich.
  assert.equal(formatShortDate("2026-01-01"), "01 Jan 2026");
});

test("a missing date renders as a dash rather than blank", () => {
  assert.equal(formatShortDate(null), "-");
  assert.equal(formatShortDate(undefined), "-");
});

test("the available figure reads as consumed against the allowance", () => {
  assert.equal(formatAvailable(2, 4), "2h / 4h");
  assert.equal(formatAvailable(0, 4), "0h / 4h");
  assert.equal(formatAvailable(4, 4), "4h / 4h");
});

// ── detail-page action visibility ───────────────────────────────────────────

const req = (status: PermissionStatus, employee_id = "emp-2") => ({
  status,
  employee_id,
});

test("a reviewer may review somebody else's pending request", () => {
  assert.equal(canReviewPermission(req("pending"), true, "emp-1"), true);
});

test("nobody reviews their own request, reviewer or not", () => {
  assert.equal(canReviewPermission(req("pending", "emp-1"), true, "emp-1"), false);
});

test("a non-reviewer never sees review actions", () => {
  assert.equal(canReviewPermission(req("pending"), false, "emp-1"), false);
});

// Phase 4D: reviewer-ness is a boolean, not a role, so a Project Head - whose
// role stays "employee" - gets the same actions a PM does on a request routed to
// their project. The routing itself is checked server-side on every decision.
test("a Project Head passed as a reviewer gets the same actions a PM does", () => {
  assert.equal(canReviewPermission(req("pending"), true, "emp-1"), true);
  assert.equal(canReviewPermission(req("pending", "emp-1"), true, "emp-1"), false);
});

test("a settled request offers no review actions to anyone", () => {
  for (const status of ["approved", "rejected", "cancelled"] as PermissionStatus[]) {
    assert.equal(canReviewPermission(req(status), true, "emp-1"), false, status);
  }
});

test("review and cancel are never both offered on the same request", () => {
  const statuses: PermissionStatus[] = ["pending", "approved", "rejected", "cancelled"];
  for (const status of statuses) {
    // Own request: cancel may be offered, review must not.
    const own = { status, employee_id: ME, permission_date: FUTURE };
    const both =
      canReviewPermission(own, true, ME) && canCancelPermission(own, ME, TODAY);
    assert.equal(both, false, status);
  }
});
