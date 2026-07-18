/**
 * Regression guard for the benchmark cycle selector.
 *
 * The dropdown once shipped with only "Current Week" / "Previous Week" visible.
 * These tests pin the single source of truth the menu iterates (WEEK_OFFSETS)
 * and the URL guard that decides whether ?weekOffset=2 / 3 survive a refresh.
 *
 * Runs on Node's built-in test runner with native TypeScript type stripping -
 * no test framework dependency is added to the app:
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  isWeekOffset,
  MAX_WEEK_OFFSET,
  WEEK_OFFSET_LABEL,
  WEEK_OFFSETS,
  type WeekOffset,
  // Explicit extension: Node's ESM resolver does not guess it the way the
  // Next/webpack resolver does.
} from "./types.ts";

test("the dropdown offers exactly four cycles", () => {
  assert.equal(WEEK_OFFSETS.length, 4);
  assert.deepEqual([...WEEK_OFFSETS], [0, 1, 2, 3]);
});

test("every offered cycle has a label, in menu order", () => {
  assert.deepEqual(
    WEEK_OFFSETS.map((o) => WEEK_OFFSET_LABEL[o]),
    ["Current week", "Previous week", "2 weeks ago", "3 weeks ago"],
  );
});

test("the URL guard accepts 2 and 3, not just 0 and 1", () => {
  // The exact regression: a guard that only accepted current/previous would
  // silently drop ?weekOffset=2 and =3 back to the current cycle on refresh.
  for (const offset of [0, 1, 2, 3]) {
    assert.equal(isWeekOffset(offset), true, `offset ${offset} must be accepted`);
  }
});

test("the URL guard rejects out-of-range and non-integer values", () => {
  for (const bad of [-1, 4, 99, 1.5, Number.NaN]) {
    assert.equal(isWeekOffset(bad), false, `${bad} must be rejected`);
  }
});

test("MAX_WEEK_OFFSET matches the offered range", () => {
  assert.equal(MAX_WEEK_OFFSET, 3);
  assert.equal(WEEK_OFFSETS[WEEK_OFFSETS.length - 1], MAX_WEEK_OFFSET);
  // A value one past the maximum must not be a WeekOffset.
  assert.equal(isWeekOffset(MAX_WEEK_OFFSET + 1), false);
});

test("labels are unique so two menu rows can never read the same", () => {
  const labels = WEEK_OFFSETS.map((o: WeekOffset) => WEEK_OFFSET_LABEL[o]);
  assert.equal(new Set(labels).size, labels.length);
});
