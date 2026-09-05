/**
 * How a half-day leave request is DISPLAYED, everywhere it is displayed.
 *
 * THE BUG THIS PINS DOWN
 * ======================
 * Phase 2 stored `half_day_period` and put it on every response, and then
 * nothing read it. Each Type cell composed its text from `classification`
 * alone - and a half-day request classifies Normal, because one working day is
 * <= 3 - so a request filed as Half Day (First) was shown as "Normal" in the
 * pending queue, in the employee's own history, on the detail page and in the
 * approver's email, with a Duration of "1 day".
 *
 * `leaveTypeLabel` and `leaveRequestDuration` are the two composers every one of
 * those surfaces now goes through, so the precedence is asserted once here
 * rather than once per component - the repo has no DOM test runner, and the way
 * a rule is made testable is to keep it out of the JSX.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  LEAVE_CLASSIFICATION_LABEL,
  LEAVE_HALF_DAY_DURATION,
  LEAVE_HALF_DAY_LABEL,
  formatLeaveDuration,
  leaveRequestDuration,
  leaveTypeLabel,
} from "./types.ts";
import type { LeaveClassification, LeaveHalfDayPeriod } from "./types.ts";

/** The two fields every Type cell reads, and nothing else. */
function typeOf(
  classification: LeaveClassification,
  half_day_period: LeaveHalfDayPeriod | null,
): string {
  return leaveTypeLabel({ classification, half_day_period });
}

function durationOf(
  working_days: number,
  half_day_period: LeaveHalfDayPeriod | null,
): string {
  return leaveRequestDuration({ working_days, half_day_period });
}

// ---------- the half wins, and reads exactly as the product specified --------

test("a first_half request displays Half Day (First)", () => {
  assert.equal(typeOf("normal", "first_half"), "Half Day (First)");
});

test("a second_half request displays Half Day (Second)", () => {
  assert.equal(typeOf("normal", "second_half"), "Half Day (Second)");
});

test("the half beats the classification the request also carries", () => {
  // THE CENTRAL ASSERTION. A half-day request HAS a classification - the
  // backend derives Normal from its one working day - and the reported bug is
  // exactly that the classification was shown instead of the half.
  assert.equal(typeOf("normal", "first_half"), "Half Day (First)");
  assert.notEqual(typeOf("normal", "first_half"), "Normal");
  // And it wins over Special too, so no length of range can resurrect the old
  // reading. (The API refuses a multi-day half day, so this is defence in
  // depth rather than a shape that can be filed.)
  assert.equal(typeOf("special", "second_half"), "Half Day (Second)");
});

test("the wording is the dropdown's own, character for character", () => {
  assert.equal(typeOf("normal", "first_half"), LEAVE_HALF_DAY_LABEL.first_half);
  assert.equal(typeOf("normal", "second_half"), LEAVE_HALF_DAY_LABEL.second_half);
});

test("no displayed type carries a technical name or a dash", () => {
  for (const period of ["first_half", "second_half"] as const) {
    const label = typeOf("normal", period);
    assert.ok(!label.includes("_"), label);
    assert.ok(!label.includes("—") && !label.includes("–"), label);
  }
});

// ---------- Normal and Special are untouched --------------------------------

test("a Normal request still displays Normal", () => {
  assert.equal(typeOf("normal", null), "Normal");
  assert.equal(typeOf("normal", null), LEAVE_CLASSIFICATION_LABEL.normal);
});

test("a Special request still displays Special", () => {
  assert.equal(typeOf("special", null), "Special");
  assert.equal(typeOf("special", null), LEAVE_CLASSIFICATION_LABEL.special);
});

test("every full-day request reads exactly as the classification map says", () => {
  // The existing classification system is not replaced, only deferred to. If a
  // third classification is ever added, this keeps the fallback honest.
  for (const classification of ["normal", "special"] as const) {
    assert.equal(
      typeOf(classification, null),
      LEAVE_CLASSIFICATION_LABEL[classification],
    );
  }
});

// ---------- Duration --------------------------------------------------------

test("a half-day request's duration is 0.5 day", () => {
  assert.equal(durationOf(1, "first_half"), "0.5 day");
  assert.equal(durationOf(1, "second_half"), "0.5 day");
  assert.equal(durationOf(1, "first_half"), LEAVE_HALF_DAY_DURATION);
});

test("the half-day duration is singular - half of one day is not 0.5 days", () => {
  assert.ok(!LEAVE_HALF_DAY_DURATION.endsWith("days"));
});

test("a half day never reports the 1 working day it covers", () => {
  // The count is honestly 1 - the day is a working day - which is why the raw
  // count could not be left in place.
  assert.notEqual(durationOf(1, "second_half"), "1 day");
});

test("a full-day request's duration is the backend's working-day count", () => {
  assert.equal(durationOf(3, null), "3 days");
  assert.equal(durationOf(1, null), "1 day");
  assert.equal(durationOf(0, null), "0 days");
});

test("the full-day duration is still formatLeaveDuration, not a second rule", () => {
  for (const days of [0, 1, 2, 3, 11]) {
    assert.equal(durationOf(days, null), formatLeaveDuration(days));
  }
});
