import assert from "node:assert/strict";
import { test } from "node:test";

// Relative .ts import: the host-Node harness resolves no `@/` alias for values.
import {
  buildDayDetail,
  CLASSIFICATION_LABEL,
  EMPTY_VALUE,
  formatDuration,
  formatShiftTime,
  formatShiftWindow,
  statusLine,
  type DaySummaryLike,
} from "./day-detail.ts";

/** A complete scheduled day: 09:00 -> 17:30 IST, 8h 30m against 8h 30m. */
const PRESENT: DaySummaryLike = {
  first_in: "2026-07-29T03:30:00+00:00",
  last_out: "2026-07-29T12:00:00+00:00",
  worked_minutes: 510,
  scheduled_minutes: 510,
  classification: "present",
  review_required: false,
};

/** 09:10 -> 17:10 IST: 8h against a scheduled 8h 30m. Short, cause unknown. */
const SHORT: DaySummaryLike = {
  first_in: "2026-07-29T03:40:00+00:00",
  last_out: "2026-07-29T11:40:00+00:00",
  worked_minutes: 480,
  scheduled_minutes: 510,
  classification: "needs_review",
  review_required: true,
};

const ONE_PUNCH: DaySummaryLike = {
  first_in: "2026-07-29T03:40:00+00:00",
  last_out: null,
  worked_minutes: null,
  scheduled_minutes: 510,
  classification: "incomplete",
  review_required: true,
};

// ── the backend owns the verdict; this file passes it through ───────────────

test("a complete day reports both boundaries and the backend duration", () => {
  const d = buildDayDetail(PRESENT);
  assert.equal(d.classification, "present");
  assert.equal(d.firstIn, PRESENT.first_in);
  assert.equal(d.lastOut, PRESENT.last_out);
  assert.equal(d.workedMinutes, 510);
  assert.equal(d.scheduledMinutes, 510);
  assert.equal(d.reviewRequired, false);
  assert.equal(statusLine(d), "Present · 8h 30m");
});

test("the duration is taken from the API, never recomputed from the timestamps", () => {
  // Same instants, a deliberately different worked_minutes. The UI must show what
  // the backend decided - a second local calculation is exactly the drift this
  // phase removes.
  const d = buildDayDetail({ ...PRESENT, worked_minutes: 123 });
  assert.equal(d.workedMinutes, 123);
  assert.equal(statusLine(d), "Present · 2h 03m");
});

test("a short day is needs_review and is never labelled a half day", () => {
  const d = buildDayDetail(SHORT);
  assert.equal(d.classification, "needs_review");
  assert.equal(d.reviewRequired, true);
  assert.equal(statusLine(d), "Needs review · 8h 00m");
  assert.ok(!statusLine(d).toLowerCase().includes("half"));
});

// ── missing OUT / a single punch ────────────────────────────────────────────

test("one punch yields no OUT and no duration", () => {
  const d = buildDayDetail(ONE_PUNCH);
  assert.equal(d.classification, "incomplete");
  assert.equal(d.lastOut, null);
  assert.equal(d.workedMinutes, null);
  assert.equal(d.reviewRequired, true);
});

test("one punch is NEVER reused as its own OUT", () => {
  const d = buildDayDetail(ONE_PUNCH);
  assert.notEqual(d.lastOut, d.firstIn);
  assert.equal(d.lastOut, null);
});

test("an incomplete day shows a bare status, never a dangling separator", () => {
  const line = statusLine(buildDayDetail(ONE_PUNCH));
  assert.equal(line, "Incomplete");
  assert.ok(!line.includes("·"));
});

// ── no biometric record ────────────────────────────────────────────────────

test("a missing row is the no-record state, with nothing fabricated", () => {
  const d = buildDayDetail(undefined);
  assert.equal(d.classification, "no_record");
  assert.equal(d.firstIn, null);
  assert.equal(d.lastOut, null);
  assert.equal(d.workedMinutes, null);
  assert.equal(statusLine(d), "No biometric record");
});

test("a missing row is flagged for review, never presented as an absence", () => {
  const d = buildDayDetail(undefined);
  assert.equal(d.reviewRequired, true);
  assert.notEqual(d.classification, "absent");
});

test("a row whose first_in is null is also no record", () => {
  const d = buildDayDetail({ ...PRESENT, first_in: null, last_out: null });
  assert.equal(d.classification, "no_record");
  assert.equal(d.workedMinutes, null);
});

// ── the official attendance record wins the status word ────────────────────

test("an existing attendance status overrides the biometric label", () => {
  // Biometric observation must never overrule the official record for the day.
  assert.equal(statusLine(buildDayDetail(PRESENT), "Leave"), "Leave · 8h 30m");
  assert.equal(statusLine(buildDayDetail(ONE_PUNCH), "Holiday"), "Holiday");
  assert.equal(statusLine(buildDayDetail(undefined), "Weekend"), "Weekend");
});

test("a null attendance label falls back to the biometric label", () => {
  assert.equal(statusLine(buildDayDetail(PRESENT), null), "Present · 8h 30m");
  assert.equal(statusLine(buildDayDetail(PRESENT), undefined), "Present · 8h 30m");
});

test("formatDuration handles the edges", () => {
  assert.equal(formatDuration(0), "0h 00m");
  assert.equal(formatDuration(5), "0h 05m");
  assert.equal(formatDuration(65), "1h 05m");
  assert.equal(formatDuration(510), "8h 30m");
  assert.equal(formatDuration(600), "10h 00m");
  assert.equal(formatDuration(545), "9h 05m");
  assert.equal(formatDuration(null), EMPTY_VALUE);
  assert.equal(formatDuration(-1), EMPTY_VALUE);
});

// ── office shift window: a plain local TIME, never zone-converted ──────────

test("formatShiftTime reads a bare local TIME without shifting it", () => {
  // 09:30 contracted must stay 09:30 - not 15:00 via a timezone conversion.
  // Read as digits (never through a timezone), rendered on the 12-hour clock.
  assert.equal(formatShiftTime("09:30:00"), "09:30 AM");
  assert.equal(formatShiftTime("17:30:00"), "05:30 PM");
  assert.equal(formatShiftTime("00:00:00"), "12:00 AM");
  assert.equal(formatShiftTime("12:00:00"), "12:00 PM");
  assert.equal(formatShiftTime("9:05"), "09:05 AM");
});

test("formatShiftTime rejects nonsense", () => {
  assert.equal(formatShiftTime(null), EMPTY_VALUE);
  assert.equal(formatShiftTime(""), EMPTY_VALUE);
  assert.equal(formatShiftTime("banana"), EMPTY_VALUE);
  assert.equal(formatShiftTime("29:00:00"), EMPTY_VALUE);
  assert.equal(formatShiftTime("09:99:00"), EMPTY_VALUE);
});

test("formatShiftWindow needs both ends", () => {
  assert.equal(formatShiftWindow("09:00:00", "17:30:00"), "09:00 AM - 05:30 PM");
  assert.equal(formatShiftWindow("09:30:00", null), null);
  assert.equal(formatShiftWindow(null, "17:30:00"), null);
  assert.equal(formatShiftWindow("banana", "17:30:00"), null);
});

// ── vocabulary ─────────────────────────────────────────────────────────────

test("exactly the four backend classifications exist, and none names a cause", () => {
  assert.deepEqual(Object.keys(CLASSIFICATION_LABEL).sort(), [
    "incomplete",
    "needs_review",
    "no_record",
    "present",
  ]);
  for (const cause of ["absent", "half_day", "permission", "leave"]) {
    assert.ok(!(cause in CLASSIFICATION_LABEL));
  }
});
