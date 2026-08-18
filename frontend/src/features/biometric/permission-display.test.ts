import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

// Relative .ts import: the host-Node harness resolves no `@/` alias for values.
import {
  buildDayDetail,
  formatPermission,
  statusLine,
  statusWithPermission,
  type DaySummaryLike,
} from "./day-detail.ts";

/**
 * Phase 12 - an APPROVED permission shown beside biometric attendance.
 *
 * The display rule in one line: `Present | 2hr · 16h 17m`. The status is still
 * the status, the duration is still the measured biometric duration, and the
 * permission is inserted between them as an additional attribute.
 *
 * These are the same pure functions the calendar cell, the day popover and the
 * PM Records table all call, so what is pinned here is exactly what renders.
 */

/** The worked example: 05:13 - 21:30 IST, 16h 17m against a 8h 30m shift. */
const LONG_DAY: DaySummaryLike = {
  first_in: "2026-08-17T23:43:00+00:00",
  last_out: "2026-08-18T16:00:00+00:00",
  worked_minutes: 16 * 60 + 17,
  scheduled_minutes: 510,
  classification: "present",
  review_required: false,
};

const withHours = (hours: number | null): DaySummaryLike => ({
  ...LONG_DAY,
  permission_hours: hours,
});

// ── the ordinary day is untouched ───────────────────────────────────────────

test("a day with no permission renders exactly as it did before Phase 12", () => {
  const detail = buildDayDetail(LONG_DAY);
  assert.equal(detail.permissionHours, null);
  assert.equal(statusLine(detail, "Present"), "Present · 16h 17m");
  assert.equal(statusWithPermission("Present", null), "Present");
  assert.equal(statusWithPermission("Present", undefined), "Present");
});

test("no permission means NO permission value at all, never a zero", () => {
  // The popover renders its Permission row only when this is non-null, so a
  // `"0hr"` here would put a row on every ordinary day.
  assert.equal(formatPermission(null), null);
  assert.equal(formatPermission(undefined), null);
  assert.equal(formatPermission(0), null);
});

// ── 1hr and 2hr ─────────────────────────────────────────────────────────────

test("an approved 1h permission renders as Present | 1hr", () => {
  const detail = buildDayDetail(withHours(1));
  assert.equal(detail.permissionHours, 1);
  assert.equal(formatPermission(1), "1hr");
  assert.equal(statusWithPermission("Present", 1), "Present | 1hr");
  assert.equal(statusLine(detail, "Present"), "Present | 1hr · 16h 17m");
});

test("an approved 2h permission renders as Present | 2hr", () => {
  const detail = buildDayDetail(withHours(2));
  assert.equal(detail.permissionHours, 2);
  assert.equal(formatPermission(2), "2hr");
  assert.equal(statusWithPermission("Present", 2), "Present | 2hr");
  assert.equal(statusLine(detail, "Present"), "Present | 2hr · 16h 17m");
});

test("the permission never replaces the status and never becomes one", () => {
  // "Present" survives verbatim at the head of the line: a permission day is a
  // present day with an attribute, not a day whose status is "Permission".
  const line = statusLine(buildDayDetail(withHours(2)), "Present");
  assert.ok(line.startsWith("Present "), line);
  assert.ok(!line.startsWith("Permission"), line);
  assert.ok(!line.includes("Leave"), line);
});

// ── biometric values are not adjusted by the permission ─────────────────────

test("the worked duration is the biometric total, not reduced by the hours", () => {
  // 16h 17m with a 2hr permission stays 16h 17m. Subtracting the permission
  // here would silently rewrite the device's own measurement.
  const plain = buildDayDetail(LONG_DAY);
  const permitted = buildDayDetail(withHours(2));
  assert.equal(permitted.workedMinutes, plain.workedMinutes);
  assert.equal(permitted.firstIn, plain.firstIn);
  assert.equal(permitted.lastOut, plain.lastOut);
  assert.equal(permitted.scheduledMinutes, plain.scheduledMinutes);
  assert.equal(permitted.classification, plain.classification);
  assert.ok(statusLine(permitted, "Present").endsWith("· 16h 17m"));
});

// ── the edges ───────────────────────────────────────────────────────────────

test("a permission on a day with no punches shows the hours and no times", () => {
  // Edge case G. The backend sends the day so the employee can see their
  // approved permission; the UI must show the hours WITHOUT inventing a
  // boundary to hang them on.
  const detail = buildDayDetail({
    first_in: null,
    last_out: null,
    worked_minutes: null,
    scheduled_minutes: 510,
    classification: "no_record",
    review_required: true,
    permission_hours: 2,
  });
  assert.equal(detail.permissionHours, 2);
  assert.equal(detail.firstIn, null);
  assert.equal(detail.lastOut, null);
  assert.equal(detail.workedMinutes, null);
  assert.equal(statusLine(detail), "No biometric record | 2hr");
});

test("a permission with no status label still states the hours", () => {
  // The calendar cell for a day nobody has ruled on. A bare "| 2hr" is not a
  // sentence, so the label is spelled out rather than left dangling.
  assert.equal(statusWithPermission(null, 2), "Permission 2hr");
  assert.equal(statusWithPermission(null, null), null);
});

test("an official status still wins over the biometric label", () => {
  // Unchanged Phase 9C behavior: the record is the authoritative word for the
  // day, and the permission attaches to whichever label won.
  const detail = buildDayDetail(withHours(1));
  assert.equal(statusLine(detail, "Leave"), "Leave | 1hr · 16h 17m");
  assert.equal(statusLine(detail), "Present | 1hr · 16h 17m");
});

// ── what must NOT come back ─────────────────────────────────────────────────
//
// This repo has no DOM test harness, so a rendered element cannot be asserted
// on. These two read the component source instead. They are narrow on purpose:
// each pins one thing Phase 12 was explicitly told not to disturb, and each
// would otherwise be pinned by nothing at all.

const read = (relative: string) =>
  readFileSync(new URL(relative, import.meta.url), "utf8");

test("the day popover keeps its four fields and adds no fifth", () => {
  const popover = read("./components/attendance-day-popover.tsx");
  assert.ok(
    !/Source/.test(popover),
    "the Phase 9C Source field was removed deliberately and must stay removed",
  );
  for (const label of ["First IN", "Last OUT", "Worked", "Scheduled"]) {
    assert.ok(popover.includes(`<Micro>${label}</Micro>`), `missing field: ${label}`);
  }
  // NO Permission field: `statusLine` below the grid already reads
  // "Present | 1hr · 6h 35m", and a row repeating it was removed at the user's
  // request on 2026-08-18. The hours reach the popover through that line only.
  assert.ok(
    !popover.includes("<Micro>Permission</Micro>"),
    "the popover must not repeat the permission as its own field",
  );
  assert.ok(popover.includes("statusLine(detail, attendanceLabel)"));
});

test("the calendar cell shows no punch times while the feed is test data", () => {
  // 2026-08-18: the line is HIDDEN, not deleted - the punches in the database
  // are backfill and must not read as this employee's real attendance. One
  // constant turns it back on when the live device feed is connected.
  const calendar = read("../attendance/components/attendance-calendar.tsx");
  assert.ok(
    /const SHOW_CALENDAR_PUNCH_TIMES = false;/.test(calendar),
    "the calendar punch line must stay hidden until real punches are connected",
  );
  assert.ok(
    calendar.includes("{SHOW_CALENDAR_PUNCH_TIMES && bio && <BiometricTimes"),
    "the punch line must be gated by that flag, not removed from the cell",
  );
  // The data flow itself is untouched: the summary query still runs, because
  // the popover, the permission indicator and Records all read it.
  assert.ok(calendar.includes("useDailySummary({ employeeId, from, to })"));
});

test("the calendar's biometric punch line is unchanged and permission-blind", () => {
  const calendar = read("../attendance/components/attendance-calendar.tsx");
  const biometricTimes = calendar.slice(
    calendar.indexOf("function BiometricTimes"),
    calendar.indexOf("export function AttendanceCalendar"),
  );
  assert.ok(biometricTimes.length > 0, "BiometricTimes must still exist");
  // Still the RAW device evidence: punch_times / kept_count, never first_in.
  assert.ok(biometricTimes.includes("summary.punch_times"));
  assert.ok(biometricTimes.includes("summary.kept_count"));
  // And it knows nothing about permissions - the hours belong on the status
  // line, never on the line that carries the Fingerprint icon.
  assert.ok(
    !/permission/i.test(biometricTimes),
    "the biometric punch line must not display permission hours",
  );
});
