import assert from "node:assert/strict";
import { test } from "node:test";

// Relative .ts import: the host-Node harness resolves no `@/` alias for values.
import {
  EMPTY_TIME,
  employeeLabel,
  formatIST,
  formatISTDate,
  formatISTTime,
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
  // 04:42Z is 10:12 IST - the exact time the EasyTime console shows.
  assert.equal(formatIST("2026-07-29T04:42:10+00:00"), "29 Jul 2026, 10:12");
});

test("formatIST shifts the date across the IST day boundary", () => {
  // 19:30Z on the 28th is 01:00 IST on the 29th.
  assert.equal(formatIST("2026-07-28T19:30:00+00:00"), "29 Jul 2026, 01:00");
});

test("formatISTDate drops the time", () => {
  assert.equal(formatISTDate("2026-08-11T12:30:00+00:00"), "11 Aug 2026");
});

test("formatISTTime renders the IST clock a PM would read off the device", () => {
  // Real row: EMP133 on 2026-07-29 arrived 09:19 IST and left 18:03 IST.
  assert.equal(formatISTTime("2026-07-29T03:49:00+00:00"), "09:19");
  assert.equal(formatISTTime("2026-07-29T12:33:00+00:00"), "18:03");
});

test("formatISTTime keeps a missing OUT column-aligned", () => {
  // A day with no last_out must not look like a formatting failure.
  assert.equal(formatISTTime(null), EMPTY_TIME);
  assert.equal(formatISTTime(undefined), EMPTY_TIME);
  assert.equal(formatISTTime("not-a-date"), EMPTY_TIME);
  assert.equal(EMPTY_TIME.length, 5);
});

test("formatISTTime crosses the IST midnight boundary", () => {
  // 19:30Z on the 28th is 01:00 IST on the 29th - same clock reading, next day.
  assert.equal(formatISTTime("2026-07-28T19:30:00+00:00"), "01:00");
});

test("date helpers fall back rather than print Invalid Date", () => {
  assert.equal(formatIST(null), "-");
  assert.equal(formatIST("not-a-date"), "-");
  assert.equal(formatISTDate(undefined), "-");
});
