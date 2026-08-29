import assert from "node:assert/strict";
import { test } from "node:test";
import { formatLeaveDuration } from "./types.ts";

// The Duration line on Leave Detail. The point of these is that the number is
// the backend's `working_days` and nothing else - the page used to compute
// `(end - start) + 1` itself, which counted the Sundays, the 2nd/4th Saturdays
// and the company holidays inside a range and so disagreed with what the
// approval actually charged.

test("renders the backend count verbatim", () => {
  assert.equal(formatLeaveDuration(3), "3 days");
});

test("28-31 August 2026 shows 3 days, not the 4-day calendar span", () => {
  // The backend answers 3: Fri 28 works, Sat 29 is a 5th Saturday and works,
  // Sun 30 does not, Mon 31 works. The old span arithmetic said 4.
  const workingDays = 3;
  const spanDays =
    Math.round(
      (Date.parse("2026-08-31") - Date.parse("2026-08-28")) / 86_400_000,
    ) + 1;

  assert.equal(spanDays, 4);
  assert.equal(formatLeaveDuration(workingDays), "3 days");
});

test("a single working day is singular", () => {
  assert.equal(formatLeaveDuration(1), "1 day");
});

test("a range that is entirely non-working is 0 days, not 1", () => {
  // A holiday-only or weekend-only range costs nothing. The old helper could
  // never say this: its floor was 1.
  assert.equal(formatLeaveDuration(0), "0 days");
});
