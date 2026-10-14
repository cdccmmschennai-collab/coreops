import assert from "node:assert/strict";
import { test } from "node:test";

import { initialReason, isFutureDate, isPastDate, isReasonMissing } from "./date-rules.ts";

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

test("editing a past record starts with an empty reason, even if one is stored", () => {
  assert.equal(initialReason("2026-10-01", "Old reason", TODAY), "");
  assert.equal(initialReason("2026-10-01", null, TODAY), "");
  // Today and the future keep the stored reason so a save does not erase it.
  assert.equal(initialReason(TODAY, "Old reason", TODAY), "Old reason");
  assert.equal(initialReason("2026-11-01", "Planned", TODAY), "Planned");
  assert.equal(initialReason(TODAY, null, TODAY), "");
});
