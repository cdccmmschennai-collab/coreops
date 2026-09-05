/**
 * Phase 4A - what an employee half-day leave LOOKS LIKE in Records and in the
 * Attendance Day Ledger.
 *
 * TWO ROWS, ONE STATUS, TWO MEANINGS
 * ==================================
 * `attendance_records` carries the half in two shapes that are deliberately
 * indistinguishable by status alone:
 *
 *   status = half_day, leave_day_fraction = 0.5    employee-approved half-day
 *                                                  leave; costs 0.5 of the pool
 *   status = half_day, leave_day_fraction = NULL   a PM / manual / company half
 *                                                  day; costs nothing
 *
 * The fraction is the domain fact that tells them apart, and `leaveDayCredit`
 * in `day-status.ts` is the only thing that reads it. Nothing in this file
 * prices anything, and nothing here may ever grow a rule of the form
 * `status === "half_day" => half-day leave` - that is the exact regression the
 * fraction exists to prevent.
 *
 * WHAT THIS FILE PINS
 * ===================
 * The DISPLAY split, which runs the other way round from the accounting one:
 *
 *   Type cell (a LEAVE REQUEST)     "Half Day (First)" / "Half Day (Second)"
 *   Attendance status (a DAY)       the plain half-day status, both shapes
 *
 * The first/second half is a fact about the REQUEST the employee filed, and it
 * lives on `leave_requests.half_day_period`. It is not a fact about the day:
 * `AttendanceOut` and `DailyReviewRowOut` carry no such field, so the ledger
 * has nothing to name a half with and must not invent one. A manual half day
 * has no half to name at all, and would be the first thing an invented rule got
 * wrong.
 *
 * The repo has no DOM test harness, so the rules are asserted through the pure
 * helpers the components call, plus narrow source reads for the two surfaces
 * whose label is written in JSX.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { leaveDayCredit, resolveAttendanceDay } from "./day-status.ts";
import { ATTENDANCE_STATUS_LABEL } from "./schemas.ts";
import { allRequestTypeLabel, type AllRequest } from "../leave/all-requests.ts";
import {
  leaveRequestDuration,
  leaveTypeLabel,
  type LeaveHalfDayPeriod,
} from "../leave/types.ts";

/** The wording that must never reach an attendance status, in every spelling
 *  the two phases have used for it - the replaced Phase 1 form included. */
const HALF_MARKERS = [
  "Half Day (First)",
  "Half Day (Second)",
  "1st Half",
  "2nd Half",
  "first_half",
  "second_half",
  "half_day_period",
];

/** An employee-approved half-day leave day, as `effects.apply_leave_approved`
 *  writes it. */
const EMPLOYEE_HALF = { status: "half_day" as const, leave_day_fraction: 0.5 };

/** A PM / manual / company half day: the SAME status, and no fraction. */
const COMPANY_HALF = { status: "half_day" as const, leave_day_fraction: null };

const read = (relative: string) =>
  readFileSync(new URL(relative, import.meta.url), "utf8");

/** One row of the mixed All Requests table, which is the widest Type column in
 *  the app - it has to name leave AND permission in one column. */
function allRequestRow(half: LeaveHalfDayPeriod | null): AllRequest {
  return {
    id: "lr-1",
    kind: "leave",
    employee_id: "emp-1",
    employee_name: "Sowrish Kumar S",
    from_date: "2027-03-03",
    to_date: "2027-03-03",
    status: "approved",
    reason: "Clinic",
    manager_id: null,
    manager_name: null,
    created_at: "2027-02-20T04:00:00Z",
    classification: "normal",
    working_days: 1,
    half_day_period: half,
    period: null,
    duration_hours: null,
  };
}

// ---------- 1-2. the Type column, where the half BELONGS ---------------------

test("a first-half leave is typed Half Day (First) in every Type column", () => {
  // `leaveTypeLabel` is what My leave, the pending queue, the cancellation queue
  // and Leave Detail all render; `allRequestTypeLabel` defers to it rather than
  // spelling the wording a second time. Asserting both is what keeps the mixed
  // table from drifting away from the three leave-only ones.
  const req = { classification: "normal" as const, half_day_period: "first_half" as const };
  assert.equal(leaveTypeLabel(req), "Half Day (First)");
  assert.equal(allRequestTypeLabel(allRequestRow("first_half")), "Half Day (First)");
  // The half is the MORE SPECIFIC fact and wins. A half day covers one working
  // day, so the backend still classifies it Normal underneath - which is what
  // the Type cell used to show.
  assert.notEqual(leaveTypeLabel(req), "Normal");
});

test("a second-half leave is typed Half Day (Second) in every Type column", () => {
  const req = { classification: "normal" as const, half_day_period: "second_half" as const };
  assert.equal(leaveTypeLabel(req), "Half Day (Second)");
  assert.equal(allRequestTypeLabel(allRequestRow("second_half")), "Half Day (Second)");
});

test("the replaced Phase 1 wording is gone from both Type composers", () => {
  // The first spelling put the half after a separator - "1st Half" / "2nd Half"
  // - and was replaced outright. It may not come back through either composer.
  for (const period of ["first_half", "second_half"] as const) {
    const label = leaveTypeLabel({ classification: "normal", half_day_period: period });
    assert.ok(!/\dst Half|\dnd Half/.test(label), `ordinal wording returned: ${label}`);
    assert.equal(allRequestTypeLabel(allRequestRow(period)), label);
  }
});

// ---------- 3-4. the attendance status, where the half does NOT belong -------

test("the attendance status for a half day names no half", () => {
  const label = ATTENDANCE_STATUS_LABEL.half_day;
  // Pinned as one literal so a reword is a deliberate, visible edit. NOTE the
  // lower-case "day": this is the wording `attendance_records` has used since
  // long before half-day leave existed, and Phase 4A changed no attendance
  // status label.
  assert.equal(label, "Half day");
  for (const marker of HALF_MARKERS) {
    assert.ok(!label.includes(marker), `the status must not carry "${marker}"`);
  }
});

test("the Day Ledger resolves both half-day shapes to the same plain status", () => {
  // THE CENTRAL ASSERTION of the ledger half. `resolveAttendanceDay` is the one
  // resolution the calendar cell and the day popover both call, and the ONLY
  // day fact it reads is the status - an employee half-day leave and a company
  // half day are the same key, so they are the same label on screen.
  for (const row of [EMPLOYEE_HALF, COMPANY_HALF]) {
    assert.deepEqual(resolveAttendanceDay({ recordStatus: row.status }), {
      key: "half_day",
      source: "record",
    });
  }
});

test("the calendar cell and the day popover carry no half-day period", () => {
  // The Day Ledger's label is written in JSX, so it is read as source. The
  // calendar owns its own `STATUS` map (colours as well as wording) and the
  // popover renders whatever label the calendar hands it, so pinning the
  // calendar's entry pins both.
  const calendar = read("./components/attendance-calendar.tsx");
  assert.ok(
    /half_day:\s*\{[^}]*label:\s*"Half day"\s*\}/.test(calendar),
    "the calendar's half-day label must stay the plain attendance status",
  );
  for (const surface of [
    "./components/attendance-calendar.tsx",
    "../biometric/components/attendance-day-popover.tsx",
  ]) {
    const source = read(surface);
    for (const marker of ["Half Day (First)", "Half Day (Second)", "half_day_period"]) {
      assert.ok(!source.includes(marker), `${surface} must not carry "${marker}"`);
    }
  }
});

// ---------- 5-6. the manual / company half day -------------------------------

test("a manual half day displays exactly as an employee half-day leave does", () => {
  // Same status, so the same cell. The reader is told what the DAY was; what it
  // COST is a different question, asked below and answered by the fraction.
  assert.equal(
    resolveAttendanceDay({ recordStatus: COMPANY_HALF.status })?.key,
    resolveAttendanceDay({ recordStatus: EMPLOYEE_HALF.status })?.key,
  );
});

test("a manual half day is never classified as a first or second half", () => {
  // THE REGRESSION THIS PHASE MUST NOT CAUSE. A PM's company half day has no
  // half on record and none that could be guessed; the only surface allowed to
  // name a half is a LEAVE REQUEST, which a manual attendance row is not. There
  // is no `half_day_period` anywhere on the attendance side to read, and these
  // two Records surfaces must never grow one.
  for (const surface of [
    "./components/attendance-records.tsx",
    "./components/record-decision-dialog.tsx",
  ]) {
    const source = read(surface);
    for (const marker of HALF_MARKERS) {
      assert.ok(!source.includes(marker), `${surface} must not carry "${marker}"`);
    }
  }
});

test("display is identical while cost is not - the fraction is the only teller", () => {
  // Stated together on purpose: the two rows look the same and are worth
  // different amounts, which is precisely why no display rule may be derived
  // from the status and no pricing rule may be derived from the label.
  assert.equal(leaveDayCredit(EMPLOYEE_HALF), 0.5);
  assert.equal(leaveDayCredit(COMPANY_HALF), 0);
});

// ---------- 7-8. what Phase 4A left alone ------------------------------------

test("a full-day leave is unchanged in both the Type column and the ledger", () => {
  assert.equal(
    leaveTypeLabel({ classification: "normal", half_day_period: null }),
    "Normal",
  );
  assert.equal(leaveRequestDuration({ working_days: 3, half_day_period: null }), "3 days");
  assert.equal(leaveRequestDuration({ working_days: 1, half_day_period: null }), "1 day");
  // A full-day leave writes `leave`, not `half_day` - a different status, a
  // different cell, and a whole day off the pool.
  assert.equal(ATTENDANCE_STATUS_LABEL.leave, "Leave");
  assert.equal(resolveAttendanceDay({ recordStatus: "leave" })?.key, "leave");
  assert.equal(leaveDayCredit({ status: "leave", leave_day_fraction: null }), 1);
});

test("Normal and Special still decide every request that has no half", () => {
  assert.equal(
    leaveTypeLabel({ classification: "special", half_day_period: null }),
    "Special",
  );
  assert.equal(allRequestTypeLabel(allRequestRow(null)), "Normal");
  // And the half-day Duration wording is the only place the two disagree.
  assert.equal(
    leaveRequestDuration({ working_days: 1, half_day_period: "first_half" }),
    "0.5 day",
  );
});
