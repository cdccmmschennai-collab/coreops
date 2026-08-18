import assert from "node:assert/strict";
import { test } from "node:test";

// Relative .ts import: the host-Node harness resolves no `@/` alias for values.
import {
  EMPTY_TIME,
  employeeLabel,
  formatIST,
  formatISTDate,
  formatISTTime,
  istTimeInputValue,
  to12Hour,
} from "./mapping-format.ts";

test("employeeLabel joins code and name", () => {
  assert.equal(employeeLabel("EMP061", "Asha Rao"), "EMP061 - Asha Rao");
});

test("employeeLabel survives a missing half", () => {
  assert.equal(employeeLabel("EMP061", null), "EMP061");
  assert.equal(employeeLabel(null, "Asha Rao"), "Asha Rao");
  assert.equal(employeeLabel(null, null), "-");
  assert.equal(employeeLabel("", "  "), "-");
});

test("formatIST renders the Asia/Kolkata wall clock, not the host zone", () => {
  // 04:42Z is 10:12 IST - the same instant the EasyTime console shows, on the
  // 12-hour clock CoreOps displays.
  assert.equal(formatIST("2026-07-29T04:42:10+00:00"), "29 Jul 2026, 10:12 AM");
});

test("formatIST shifts the date across the IST day boundary", () => {
  // 19:30Z on the 28th is 01:00 IST on the 29th.
  assert.equal(formatIST("2026-07-28T19:30:00+00:00"), "29 Jul 2026, 01:00 AM");
});

test("formatISTDate drops the time", () => {
  assert.equal(formatISTDate("2026-08-11T12:30:00+00:00"), "11 Aug 2026");
});

test("formatISTTime renders the IST clock a PM would read off the device", () => {
  // Real row: EMP133 on 2026-07-29 arrived 09:19 and left 18:03 IST - shown on
  // the 12-hour clock, so the afternoon punch reads 06:03 PM, never 18:03.
  assert.equal(formatISTTime("2026-07-29T03:49:00+00:00"), "09:19 AM");
  assert.equal(formatISTTime("2026-07-29T12:33:00+00:00"), "06:03 PM");
});

test("the 12-hour clock names noon and midnight correctly", () => {
  // The two readings a naive `hour % 12` gets wrong: both must be 12, not 00.
  assert.equal(to12Hour(12, 0), "12:00 PM");
  assert.equal(to12Hour(0, 0), "12:00 AM");
  assert.equal(to12Hour(13, 5), "01:05 PM");
  assert.equal(to12Hour(23, 59), "11:59 PM");
  assert.equal(to12Hour(9, 7), "09:07 AM");
  // 06:30Z is 12:00 IST exactly - noon through the real conversion, not just
  // through the arithmetic.
  assert.equal(formatISTTime("2026-07-29T06:30:00+00:00"), "12:00 PM");
  assert.equal(formatISTTime("2026-07-28T18:30:00+00:00"), "12:00 AM");
});

test("the time-input value stays 24-hour, because the input demands it", () => {
  // `<input type="time">` rejects "05:30 PM" and blanks itself, so the PM
  // decision dialog must prefill from this, never from formatISTTime.
  assert.equal(istTimeInputValue("2026-07-29T12:33:00+00:00"), "18:03");
  assert.equal(istTimeInputValue("2026-07-29T03:49:00+00:00"), "09:19");
  assert.equal(istTimeInputValue("2026-07-28T18:30:00+00:00"), "00:00");
  assert.match(istTimeInputValue("2026-07-29T06:30:00+00:00"), /^\d{2}:\d{2}$/);
  // No value means an empty input, not a dash.
  assert.equal(istTimeInputValue(null), "");
  assert.equal(istTimeInputValue("not-a-date"), "");
});

test("formatISTTime keeps a missing OUT column-aligned", () => {
  // A day with no last_out must not look like a formatting failure.
  assert.equal(formatISTTime(null), EMPTY_TIME);
  assert.equal(formatISTTime(undefined), EMPTY_TIME);
  assert.equal(formatISTTime("not-a-date"), EMPTY_TIME);
  assert.equal(EMPTY_TIME.length, "09:19 AM".length);
});

test("formatISTTime crosses the IST midnight boundary", () => {
  // 19:30Z on the 28th is 01:00 IST on the 29th - same clock reading, next day.
  assert.equal(formatISTTime("2026-07-28T19:30:00+00:00"), "01:00 AM");
});

test("date helpers fall back rather than print Invalid Date", () => {
  assert.equal(formatIST(null), "-");
  assert.equal(formatIST("not-a-date"), "-");
  assert.equal(formatISTDate(undefined), "-");
});
