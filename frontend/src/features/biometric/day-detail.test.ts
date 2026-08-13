import assert from "node:assert/strict";
import { test } from "node:test";

// Relative .ts import: the host-Node harness resolves no `@/` alias for values.
import {
  buildDayDetail,
  EMPTY_VALUE,
  formatDuration,
  formatShiftTime,
  formatShiftWindow,
  minutesBetween,
  statusLine,
  STATUS_LABEL,
  type DaySummaryLike,
} from "./day-detail.ts";

/** A complete day: 09:10 -> 17:10 IST, which is 03:40Z -> 11:40Z. */
const COMPLETE: DaySummaryLike = {
  first_in: "2026-07-29T03:40:00+00:00",
  last_out: "2026-07-29T11:40:00+00:00",
};

const ONE_PUNCH: DaySummaryLike = {
  first_in: "2026-07-29T03:40:00+00:00",
  last_out: null,
};

// ── edge case 1: a normal two-punch day ─────────────────────────────────────

test("a complete day reports both boundaries and a display duration", () => {
  const d = buildDayDetail(COMPLETE);
  assert.equal(d.status, "complete");
  assert.equal(d.firstIn, COMPLETE.first_in);
  assert.equal(d.lastOut, COMPLETE.last_out);
  assert.equal(d.totalMinutes, 480);
  assert.equal(statusLine(d), "Present · 8h 00m");
});

// ── edge cases 2 and 3: missing OUT / a single punch ────────────────────────

test("one punch yields no OUT and no duration", () => {
  const d = buildDayDetail(ONE_PUNCH);
  assert.equal(d.status, "partial");
  assert.equal(d.lastOut, null);
  assert.equal(d.totalMinutes, null);
});

test("one punch is NEVER reused as its own OUT", () => {
  const d = buildDayDetail(ONE_PUNCH);
  assert.notEqual(d.lastOut, d.firstIn);
  assert.equal(d.lastOut, null);
});

test("an incomplete day shows a bare status, never a dangling separator", () => {
  const line = statusLine(buildDayDetail(ONE_PUNCH));
  assert.equal(line, "Partial");
  assert.ok(!line.includes("·"));
});

// ── edge case 4: no biometric record ───────────────────────────────────────

test("a missing row is the no-record state, with nothing fabricated", () => {
  const d = buildDayDetail(undefined);
  assert.equal(d.status, "no_record");
  assert.equal(d.firstIn, null);
  assert.equal(d.lastOut, null);
  assert.equal(d.totalMinutes, null);
  assert.equal(statusLine(d), "No biometric record");
});

test("a row whose first_in is null is also no record", () => {
  assert.equal(buildDayDetail({ first_in: null, last_out: null }).status, "no_record");
});

// ── the official attendance record wins the status word ────────────────────

test("an existing attendance status overrides the biometric label", () => {
  // Biometric observation must never overrule the official record for the day.
  assert.equal(statusLine(buildDayDetail(COMPLETE), "Leave"), "Leave · 8h 00m");
  assert.equal(statusLine(buildDayDetail(ONE_PUNCH), "Holiday"), "Holiday");
  assert.equal(statusLine(buildDayDetail(undefined), "Weekend"), "Weekend");
});

test("a null attendance label falls back to the biometric label", () => {
  assert.equal(statusLine(buildDayDetail(COMPLETE), null), "Present · 8h 00m");
  assert.equal(statusLine(buildDayDetail(COMPLETE), undefined), "Present · 8h 00m");
});

// ── total hours: display only, and only when both boundaries exist ─────────

test("minutesBetween needs both ends", () => {
  assert.equal(minutesBetween(COMPLETE.first_in, null), null);
  assert.equal(minutesBetween(null, COMPLETE.last_out), null);
  assert.equal(minutesBetween(undefined, undefined), null);
});

test("minutesBetween refuses a negative span rather than showing 0h 00m", () => {
  assert.equal(
    minutesBetween("2026-07-29T11:40:00+00:00", "2026-07-29T03:40:00+00:00"),
    null,
  );
});

test("minutesBetween rejects unparseable input", () => {
  assert.equal(minutesBetween("not-a-date", COMPLETE.last_out), null);
});

test("formatDuration handles the edges", () => {
  assert.equal(formatDuration(0), "0h 00m");
  assert.equal(formatDuration(5), "0h 05m");
  assert.equal(formatDuration(65), "1h 05m");
  assert.equal(formatDuration(600), "10h 00m");
  assert.equal(formatDuration(545), "9h 05m");
  assert.equal(formatDuration(null), EMPTY_VALUE);
  assert.equal(formatDuration(-1), EMPTY_VALUE);
});

// ── office shift window: a plain local TIME, never zone-converted ──────────

test("formatShiftTime reads a bare local TIME without shifting it", () => {
  // 09:30 contracted must stay 09:30 - not 15:00 via a timezone conversion.
  assert.equal(formatShiftTime("09:30:00"), "09:30");
  assert.equal(formatShiftTime("17:30:00"), "17:30");
  assert.equal(formatShiftTime("00:00:00"), "00:00");
  assert.equal(formatShiftTime("9:05"), "09:05");
});

test("formatShiftTime rejects nonsense", () => {
  assert.equal(formatShiftTime(null), EMPTY_VALUE);
  assert.equal(formatShiftTime(""), EMPTY_VALUE);
  assert.equal(formatShiftTime("banana"), EMPTY_VALUE);
  assert.equal(formatShiftTime("29:00:00"), EMPTY_VALUE);
  assert.equal(formatShiftTime("09:99:00"), EMPTY_VALUE);
});

test("formatShiftWindow needs both ends", () => {
  assert.equal(formatShiftWindow("09:00:00", "17:30:00"), "09:00 - 17:30");
  assert.equal(formatShiftWindow("09:30:00", null), null);
  assert.equal(formatShiftWindow(null, "17:30:00"), null);
  assert.equal(formatShiftWindow("banana", "17:30:00"), null);
});

// ── vocabulary ─────────────────────────────────────────────────────────────

test("only the three supported completeness states exist", () => {
  assert.deepEqual(Object.keys(STATUS_LABEL).sort(), [
    "complete",
    "no_record",
    "partial",
  ]);
});
