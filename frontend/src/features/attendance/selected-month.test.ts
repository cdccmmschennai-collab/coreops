import assert from "node:assert/strict";
import { test } from "node:test";

// Relative .ts import: the host-Node harness resolves no `@/` alias for values.
import {
  businessMonthKey,
  isCurrentMonthKey,
  isPastMonthKey,
  monthKey,
  monthKeyLabel,
  normalizeMonthKey,
  parseMonthKey,
  shiftMonthKey,
  shortMonthLabel,
  withMonth,
} from "./selected-month.ts";

const AUGUST = "2026-08-01";
const SEPTEMBER = "2026-09-01";

// ── the month key ───────────────────────────────────────────────────────────

test("monthKey builds a first-of-month from a 0-indexed month", () => {
  assert.equal(monthKey(2026, 7), "2026-08-01");
  assert.equal(monthKey(2026, 0), "2026-01-01");
  assert.equal(monthKey(2026, 11), "2026-12-01");
});

test("monthKey rolls the year rather than inventing a 13th month", () => {
  assert.equal(monthKey(2026, 12), "2027-01-01");
  assert.equal(monthKey(2026, -1), "2025-12-01");
});

test("parseMonthKey accepts any date inside the month", () => {
  assert.deepEqual(parseMonthKey("2026-08-01"), { y: 2026, m: 7 });
  assert.deepEqual(parseMonthKey("2026-08-31"), { y: 2026, m: 7 });
  assert.equal(parseMonthKey("banana"), null);
  assert.equal(parseMonthKey("2026-13-01"), null);
});

test("a junk URL value falls back to the current month", () => {
  assert.equal(normalizeMonthKey("banana", AUGUST), AUGUST);
  assert.equal(normalizeMonthKey("", AUGUST), AUGUST);
  // A real value is kept, and normalised to the 1st.
  assert.equal(normalizeMonthKey("2026-09-17", AUGUST), SEPTEMBER);
});

// ── stepping through months (the calendar's Prev/Next) ──────────────────────

test("shiftMonthKey crosses both year boundaries", () => {
  assert.equal(shiftMonthKey(AUGUST, 1), SEPTEMBER);
  assert.equal(shiftMonthKey(SEPTEMBER, -1), AUGUST);
  assert.equal(shiftMonthKey("2026-12-01", 1), "2027-01-01");
  assert.equal(shiftMonthKey("2026-01-01", -1), "2025-12-01");
});

test("stepping away and back restores exactly the month you left", () => {
  // The property the KPI cards depend on: August -> September -> October -> back
  // must land on the same key, because the key IS the query key.
  let month = AUGUST;
  for (const delta of [1, 1, -1, -1]) month = shiftMonthKey(month, delta);
  assert.equal(month, AUGUST);
});

// ── which month is "now" ────────────────────────────────────────────────────

test("the current month is the Chennai business month, not the UTC one", () => {
  // 2026-08-31 21:00 UTC is already 2026-09-01 02:30 IST, so the page must have
  // rolled over to September.
  const justAfterISTMidnight = new Date("2026-08-31T21:00:00Z");
  assert.equal(businessMonthKey(justAfterISTMidnight), SEPTEMBER);
  // ...and half an hour earlier it is still August.
  assert.equal(businessMonthKey(new Date("2026-08-31T18:00:00Z")), AUGUST);
});

test("current / past are decided against the given month, with no clock", () => {
  assert.ok(isCurrentMonthKey(SEPTEMBER, SEPTEMBER));
  assert.ok(isCurrentMonthKey("2026-09-30", SEPTEMBER));
  assert.ok(!isCurrentMonthKey(AUGUST, SEPTEMBER));

  assert.ok(isPastMonthKey(AUGUST, SEPTEMBER));
  assert.ok(!isPastMonthKey(SEPTEMBER, SEPTEMBER));
  // A future month is not a past one - filing ahead stays allowed.
  assert.ok(!isPastMonthKey("2026-10-01", SEPTEMBER));
});

// ── labels ──────────────────────────────────────────────────────────────────

test("month labels", () => {
  assert.equal(monthKeyLabel(AUGUST), "August 2026");
  assert.equal(shortMonthLabel(AUGUST), "Aug 2026");
});

test("a KPI label names its month only when it is not the current one", () => {
  assert.equal(withMonth("Leave taken", SEPTEMBER, SEPTEMBER), "Leave taken");
  assert.equal(withMonth("Leave taken", AUGUST, SEPTEMBER), "Leave taken · Aug 2026");
});
