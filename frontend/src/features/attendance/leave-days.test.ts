import assert from "node:assert/strict";
import { test } from "node:test";

// Relative .ts import: the host-Node harness resolves no `@/` alias for values.
import { formatPresentDays, leaveDayCredit, leaveDaysTaken } from "./day-status.ts";
import { isHalfStep } from "../leave-balances/types.ts";

/**
 * "Leave taken", in days.
 *
 * The tile used to be `records.filter(r => r.status === "leave").length` - a row
 * COUNT. A count and a day total agree only while every leave is a whole day, so
 * a half-day leave (a `half_day` row carrying a 0.5 fraction) added nothing and
 * the card could never render a ".5" at all. These pin the day total, and pin
 * that a bare `half_day` still costs nobody anything.
 */

const LEAVE = { status: "leave" as const };
const HALF_LEAVE = { status: "half_day" as const, leave_day_fraction: 0.5 };
const COMPANY_HALF = { status: "half_day" as const };
const PRESENT = { status: "present" as const };

// ---------- one row at a time ----------------------------------------------

test("a full leave day costs one day", () => {
  assert.equal(leaveDayCredit(LEAVE), 1);
});

test("a half-day leave costs half a day", () => {
  assert.equal(leaveDayCredit(HALF_LEAVE), 0.5);
});

test("a half day that states no fraction costs nothing", () => {
  // The 29 company-wide half-day rows on 2026-08-14. Billing these would be
  // charging 29 people for an office closure.
  assert.equal(leaveDayCredit(COMPANY_HALF), 0);
});

test("a stated zero is honoured, not treated as unstated", () => {
  assert.equal(
    leaveDayCredit({ status: "half_day", leave_day_fraction: 0 }),
    0,
  );
});

test("a null fraction falls back to the status", () => {
  assert.equal(leaveDayCredit({ status: "leave", leave_day_fraction: null }), 1);
  assert.equal(
    leaveDayCredit({ status: "half_day", leave_day_fraction: null }),
    0,
  );
});

test("a stated fraction overrides a leave row", () => {
  assert.equal(leaveDayCredit({ status: "leave", leave_day_fraction: 0.5 }), 0.5);
});

for (const status of ["present", "absent", "holiday", "weekend", "comp_off"] as const) {
  test(`${status} never costs leave, even with a fraction on it`, () => {
    assert.equal(leaveDayCredit({ status, leave_day_fraction: 1 }), 0);
  });
}

// ---------- the month roll-up ------------------------------------------------

test("case 1 - one full day is 1", () => {
  assert.equal(leaveDaysTaken([LEAVE]), 1);
});

test("case 2 - one half day is 0.5", () => {
  assert.equal(leaveDaysTaken([HALF_LEAVE]), 0.5);
});

test("case 3 - a full day plus a half day is 1.5", () => {
  // The exact production symptom: the tile read 1d.
  assert.equal(leaveDaysTaken([LEAVE, HALF_LEAVE]), 1.5);
});

test("case 4 - two half days are 1", () => {
  assert.equal(leaveDaysTaken([HALF_LEAVE, HALF_LEAVE]), 1);
});

test("present and company half days are not leave", () => {
  assert.equal(leaveDaysTaken([PRESENT, COMPANY_HALF, LEAVE]), 1);
});

test("an empty month is 0, not NaN", () => {
  assert.equal(leaveDaysTaken([]), 0);
});

test("half days sum without floating-point drift", () => {
  // Summed in halves for exactly this reason: naive 0.5 accumulation over a
  // long month is what produces "3.4999999999999996d" on a KPI card.
  const rows = Array.from({ length: 7 }, () => HALF_LEAVE);
  assert.equal(leaveDaysTaken(rows), 3.5);
});

test("the tile formats whole and half days the way Present does", () => {
  assert.equal(formatPresentDays(leaveDaysTaken([LEAVE])), "1");
  assert.equal(formatPresentDays(leaveDaysTaken([LEAVE, HALF_LEAVE])), "1.5");
  assert.equal(formatPresentDays(leaveDaysTaken([])), "0");
});

// ---------- the balance field ------------------------------------------------

for (const good of [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, -0.5, -2]) {
  test(`${good} is a valid leave balance`, () => {
    assert.equal(isHalfStep(good), true);
  });
}

for (const bad of [0.1, 0.25, 1.1, 1.25, 2.1, 2.4, 2.6, 0.75]) {
  test(`${bad} is refused as a leave balance`, () => {
    assert.equal(isHalfStep(bad), false);
  });
}

test("a non-number is not a valid balance", () => {
  assert.equal(isHalfStep(Number.NaN), false);
  assert.equal(isHalfStep(Number.POSITIVE_INFINITY), false);
});

test("the check does not inherit binary floating-point error", () => {
  // `2.4 % 0.5` is 0.3999999999999999, and a naive `% 0.5 === 0` test drifts on
  // values a manager can really type. Multiplying by 2 is exact for all of them.
  assert.equal(isHalfStep(2.4), false);
  assert.equal(isHalfStep(4.5), true);
  assert.equal(isHalfStep(1.5 + 1), true);
});
