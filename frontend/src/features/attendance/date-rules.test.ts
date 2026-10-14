import assert from "node:assert/strict";
import { test } from "node:test";

import { isFutureDate, isPastDate, isReasonMissing } from "./date-rules.ts";

const TODAY = "2026-10-14";

test("past, today and future are told apart by the IST date", () => {
  assert.ok(isPastDate("2026-10-13", TODAY));
  assert.ok(!isPastDate(TODAY, TODAY));
  assert.ok(!isPastDate("2026-10-15", TODAY));

  assert.ok(isFutureDate("2026-10-15", TODAY));
  assert.ok(!isFutureDate(TODAY, TODAY));
  assert.ok(!isFutureDate("2026-10-13", TODAY));
});

test("comparison crosses month and year boundaries", () => {
  assert.ok(isPastDate("2026-09-30", TODAY));
  assert.ok(isFutureDate("2027-01-01", TODAY));
  assert.ok(isPastDate("2025-12-31", TODAY));
});

test("a past date needs a reason; today and the future do not", () => {
  assert.ok(isReasonMissing("2026-10-01", "", TODAY));
  assert.ok(isReasonMissing("2026-10-01", "   ", TODAY));
  assert.ok(!isReasonMissing("2026-10-01", "Missed punch", TODAY));
  assert.ok(!isReasonMissing(TODAY, "", TODAY));
  assert.ok(!isReasonMissing("2026-11-01", "", TODAY));
});
