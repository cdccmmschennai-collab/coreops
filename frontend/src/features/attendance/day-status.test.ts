import assert from "node:assert/strict";
import { test } from "node:test";

// Relative .ts import: the host-Node harness resolves no `@/` alias for values.
import {
  calendarDayMaps,
  calendarDayStatus,
  formatPresentDays,
  presentDayCredit,
  presentDaysInMonth,
  resolveAttendanceDay,
  type CalendarDayEvent,
  type DailySummaryLike,
} from "./day-status.ts";

/**
 * August 2026, the month every roll-up case below uses.
 *
 *   Saturdays  1st, 8th, 15th, 22nd, 29th
 *   Sundays    2nd, 9th, 16th, 23rd, 30th
 *
 * Under the office week (`isWeekend`) the off days are every Sunday plus the
 * 2nd and 4th Saturday - the 8th and the 22nd. The 1st, 15th and 29th are
 * ordinary working Saturdays.
 */
const YEAR = 2026;
const MONTH = 7; // 0-indexed August

const WEEKDAY = "2026-08-19"; // Wednesday
const SAT_1ST = "2026-08-01";
const SAT_2ND = "2026-08-08";
const SAT_4TH = "2026-08-22";

/** A day the device saw both ends of: 09:00 -> 17:30 IST. `classify_day`
 *  settles this one as `present` server-side. */
function present(summary_date: string): DailySummaryLike {
  return {
    summary_date,
    first_in: `${summary_date}T03:30:00+00:00`,
    last_out: `${summary_date}T12:00:00+00:00`,
    worked_minutes: 510,
    scheduled_minutes: 510,
    classification: "present",
    review_required: false,
  };
}

/** One surviving punch. The device did NOT settle the day. */
function incomplete(summary_date: string): DailySummaryLike {
  return {
    summary_date,
    first_in: `${summary_date}T03:40:00+00:00`,
    last_out: null,
    worked_minutes: null,
    scheduled_minutes: 510,
    classification: "incomplete",
    review_required: true,
  };
}

/** A row with no punches at all - a PM-decided or permission-only day. */
function noRecord(summary_date: string): DailySummaryLike {
  return {
    summary_date,
    first_in: null,
    last_out: null,
    worked_minutes: null,
    scheduled_minutes: 510,
    classification: "no_record",
    review_required: true,
  };
}

const HOLIDAY: CalendarDayEvent = {
  event_date: "2026-08-17",
  title: "Independence Day (observed)",
  event_type: "holiday",
};
const CDC_HOLIDAY: CalendarDayEvent = {
  event_date: "2026-08-18",
  title: "CDC foundation day",
  event_type: "cdc_holiday",
};
const NATURAL_HAZARD: CalendarDayEvent = {
  event_date: "2026-08-20",
  title: "Cyclone warning",
  event_type: "natural_hazard",
};
/** The PM declaring an otherwise-off 2nd Saturday open. */
const WORKING_SATURDAY: CalendarDayEvent = {
  event_date: SAT_2ND,
  title: "Audit Saturday",
  event_type: "working_day",
};

// ── calendarDayStatus: tiers 3-5, the calendar on its own ───────────────────

test("a declared working day clears the holiday and the weekend", () => {
  assert.equal(
    calendarDayStatus({ declaredWorking: true, officeClosed: true, weekend: true }),
    undefined,
  );
});

test("an office-closing entry outranks the weekend", () => {
  assert.equal(calendarDayStatus({ officeClosed: true, weekend: true }), "holiday");
});

test("a weekend with nothing else on it is a weekend", () => {
  assert.equal(calendarDayStatus({ weekend: true }), "weekend");
});

test("an ordinary working day carries no calendar status", () => {
  assert.equal(calendarDayStatus({}), undefined);
});

// ── resolveAttendanceDay: the full precedence ───────────────────────────────
//
//   attendance record > biometric present > working day > holiday > weekend

test("1 - a normal weekday with a punch is Present", () => {
  assert.deepEqual(resolveAttendanceDay({ summary: present(WEEKDAY) }), {
    key: "present",
    source: "biometric",
  });
});

test("2 - a 1st Saturday with a punch is Present", () => {
  assert.deepEqual(
    resolveAttendanceDay({ weekend: false, summary: present(SAT_1ST) }),
    { key: "present", source: "biometric" },
  );
});

test("3 - a 2nd Saturday with a punch is Present with NO working-day override", () => {
  // The rule that removes the PM step: the calendar calls the day off, the
  // device says the employee was here, and the device wins.
  assert.deepEqual(
    resolveAttendanceDay({ weekend: true, summary: present(SAT_2ND) }),
    { key: "present", source: "biometric" },
  );
});

test("4 - a 2nd Saturday declared Working Day with a punch is Present", () => {
  assert.deepEqual(
    resolveAttendanceDay({
      weekend: true,
      declaredWorking: true,
      summary: present(SAT_2ND),
    }),
    { key: "present", source: "biometric" },
  );
});

test("5 - a holiday with no punch stays Holiday", () => {
  assert.deepEqual(resolveAttendanceDay({ officeClosed: true }), {
    key: "holiday",
    source: "record",
  });
});

test("6/8/10 - a holiday, CDC holiday or hazard day WITH a punch is Present", () => {
  // All three arrive here as `officeClosed`; none of them outranks the device.
  assert.deepEqual(
    resolveAttendanceDay({ officeClosed: true, summary: present("2026-08-17") }),
    { key: "present", source: "biometric" },
  );
});

test("7/9 - a CDC holiday or hazard day with no punch resolves to the holiday key", () => {
  // `AttendanceStatus` has no cdc_holiday / natural_hazard value; the cell
  // prints the entry's own title beside the status. Unchanged by this work.
  const { off } = calendarDayMaps([CDC_HOLIDAY, NATURAL_HAZARD]);
  for (const iso of [CDC_HOLIDAY.event_date, NATURAL_HAZARD.event_date]) {
    assert.deepEqual(
      resolveAttendanceDay({ officeClosed: Boolean(off.get(iso)) }),
      { key: "holiday", source: "record" },
      iso,
    );
  }
});

test("11 - a declared Working Day with no punch resolves to nothing", () => {
  // Existing behaviour: an ordinary open day nobody has ruled on and nobody
  // punched. The cell shows its green "Working" line and no status.
  assert.equal(resolveAttendanceDay({ weekend: true, declaredWorking: true }), null);
  assert.equal(resolveAttendanceDay({ declaredWorking: true }), null);
});

test("12 - a declared Working Day with a punch is Present", () => {
  assert.deepEqual(
    resolveAttendanceDay({ declaredWorking: true, summary: present(SAT_2ND) }),
    { key: "present", source: "biometric" },
  );
});

test("13 - an explicit Present record with a punch stays the record's Present", () => {
  assert.deepEqual(
    resolveAttendanceDay({ recordStatus: "present", summary: present(WEEKDAY) }),
    { key: "present", source: "record" },
  );
});

test("14 - an explicit Half day record is never overruled by a punch", () => {
  assert.deepEqual(
    resolveAttendanceDay({ recordStatus: "half_day", summary: present(WEEKDAY) }),
    { key: "half_day", source: "record" },
  );
});

test("an explicit Leave record is never overruled by a punch", () => {
  // The record is the intentional human decision, so it still wins. The
  // biometric-vs-leave guard on the server is what stops the pair being
  // created in the first place; nothing here weakens it.
  assert.deepEqual(
    resolveAttendanceDay({ recordStatus: "leave", summary: present(WEEKDAY) }),
    { key: "leave", source: "record" },
  );
});

test("an UNSETTLED punch never overrules the calendar", () => {
  // Only `present` is promoted. One punch on a holiday is a person seen once.
  assert.deepEqual(
    resolveAttendanceDay({ officeClosed: true, summary: incomplete("2026-08-17") }),
    { key: "holiday", source: "record" },
  );
  assert.deepEqual(
    resolveAttendanceDay({ weekend: true, summary: incomplete(SAT_2ND) }),
    { key: "weekend", source: "record" },
  );
  assert.deepEqual(
    resolveAttendanceDay({ weekend: true, summary: noRecord(SAT_2ND) }),
    { key: "weekend", source: "record" },
  );
  assert.equal(resolveAttendanceDay({ summary: incomplete(WEEKDAY) }), null);
});

test("a day with nothing at all resolves to nothing", () => {
  assert.equal(resolveAttendanceDay({}), null);
});

// ── presentDayCredit: what a resolved day is worth ──────────────────────────

test("Present is worth a full day whatever settled it", () => {
  assert.equal(presentDayCredit({ key: "present", source: "record" }), 1);
  assert.equal(presentDayCredit({ key: "present", source: "biometric" }), 1);
});

test("Half day is worth half a day", () => {
  assert.equal(presentDayCredit({ key: "half_day", source: "record" }), 0.5);
});

test("leave, holiday, weekend, absent, comp off and unresolved are worth nothing", () => {
  for (const key of ["leave", "holiday", "weekend", "absent", "comp_off"] as const) {
    assert.equal(presentDayCredit({ key, source: "record" }), 0, key);
  }
  assert.equal(presentDayCredit(null), 0);
});

// ── calendarDayMaps ─────────────────────────────────────────────────────────

test("calendar entries split into office-closing and declared-working", () => {
  const { off, working } = calendarDayMaps([
    HOLIDAY,
    CDC_HOLIDAY,
    NATURAL_HAZARD,
    WORKING_SATURDAY,
    { event_date: "2026-08-21", title: "Town hall", event_type: "event" },
  ]);
  assert.deepEqual([...off.keys()].sort(), [
    "2026-08-17",
    "2026-08-18",
    "2026-08-20",
  ]);
  assert.deepEqual([...working.keys()], [SAT_2ND]);
  // An informational `event` closes nothing and opens nothing.
  assert.equal(off.has("2026-08-21"), false);
  assert.equal(working.has("2026-08-21"), false);
});

// ── presentDaysInMonth: the "Present this month" card ───────────────────────

/** A month with nothing in it at all. */
function emptyMonth() {
  return { year: YEAR, month: MONTH, records: [], events: [], summaries: [] };
}

test("card 1 - normal weekday + punch adds 1.0", () => {
  assert.equal(
    presentDaysInMonth({ ...emptyMonth(), summaries: [present(WEEKDAY)] }),
    1,
  );
});

test("card 2 - 1st Saturday + punch adds 1.0", () => {
  assert.equal(
    presentDaysInMonth({ ...emptyMonth(), summaries: [present(SAT_1ST)] }),
    1,
  );
});

test("card 3 - 2nd Saturday + no override + punch adds 1.0", () => {
  assert.equal(
    presentDaysInMonth({ ...emptyMonth(), summaries: [present(SAT_2ND)] }),
    1,
  );
  // ...and the 4th Saturday behaves the same way.
  assert.equal(
    presentDaysInMonth({ ...emptyMonth(), summaries: [present(SAT_4TH)] }),
    1,
  );
});

test("card 4 - 2nd Saturday + Working Day override + punch adds 1.0", () => {
  assert.equal(
    presentDaysInMonth({
      ...emptyMonth(),
      events: [WORKING_SATURDAY],
      summaries: [present(SAT_2ND)],
    }),
    1,
  );
});

test("card 5/7/9 - holiday, CDC holiday and hazard days with no punch add nothing", () => {
  assert.equal(
    presentDaysInMonth({
      ...emptyMonth(),
      events: [HOLIDAY, CDC_HOLIDAY, NATURAL_HAZARD],
    }),
    0,
  );
});

test("card 6/8/10 - holiday, CDC holiday and hazard days WITH punches add 1.0 each", () => {
  assert.equal(
    presentDaysInMonth({
      ...emptyMonth(),
      events: [HOLIDAY, CDC_HOLIDAY, NATURAL_HAZARD],
      summaries: [
        present(HOLIDAY.event_date),
        present(CDC_HOLIDAY.event_date),
        present(NATURAL_HAZARD.event_date),
      ],
    }),
    3,
  );
});

test("card 11 - a declared Working Day with no punch adds nothing", () => {
  assert.equal(
    presentDaysInMonth({ ...emptyMonth(), events: [WORKING_SATURDAY] }),
    0,
  );
});

test("card 12 - a declared Working Day with a punch adds 1.0", () => {
  assert.equal(
    presentDaysInMonth({
      ...emptyMonth(),
      events: [WORKING_SATURDAY],
      summaries: [present(SAT_2ND)],
    }),
    1,
  );
});

test("card 13 - an explicit Present record with a punch adds 1.0, not 2.0", () => {
  assert.equal(
    presentDaysInMonth({
      ...emptyMonth(),
      records: [{ attendance_date: WEEKDAY, status: "present" }],
      summaries: [present(WEEKDAY)],
    }),
    1,
  );
});

test("card 14 - an explicit Half day record adds 0.5 even with a punch", () => {
  assert.equal(
    presentDaysInMonth({
      ...emptyMonth(),
      records: [{ attendance_date: WEEKDAY, status: "half_day" }],
      summaries: [present(WEEKDAY)],
    }),
    0.5,
  );
  // ...and with no punch at all, unchanged from before this work.
  assert.equal(
    presentDaysInMonth({
      ...emptyMonth(),
      records: [{ attendance_date: WEEKDAY, status: "half_day" }],
    }),
    0.5,
  );
});

test("approved leave with no punch adds nothing", () => {
  assert.equal(
    presentDaysInMonth({
      ...emptyMonth(),
      records: [{ attendance_date: WEEKDAY, status: "leave" }],
    }),
    0,
  );
});

test("a manually recorded Present day adds 1.0", () => {
  assert.equal(
    presentDaysInMonth({
      ...emptyMonth(),
      records: [{ attendance_date: WEEKDAY, status: "present" }],
    }),
    1,
  );
});

test("a month with no data at all is zero", () => {
  assert.equal(presentDaysInMonth(emptyMonth()), 0);
});

test("a biometric Present day with NO attendance record adds 1.0", () => {
  // The original bug: this month counted 0 until a PM went into Records and
  // typed the day in by hand.
  assert.equal(
    presentDaysInMonth({
      ...emptyMonth(),
      summaries: [present("2026-08-17"), present("2026-08-18"), present(WEEKDAY)],
    }),
    3,
  );
});

test("a PM-decided Present day whose punches are missing still counts 1.0", () => {
  // Phase 9C: the summary row exists but is biometrically `no_record`. The
  // record is what settles it, exactly as the Records screen shows.
  assert.equal(
    presentDaysInMonth({
      ...emptyMonth(),
      records: [{ attendance_date: WEEKDAY, status: "present" }],
      summaries: [noRecord(WEEKDAY)],
    }),
    1,
  );
});

test("an unsettled biometric day is never credited, on any kind of day", () => {
  assert.equal(
    presentDaysInMonth({
      ...emptyMonth(),
      events: [HOLIDAY],
      summaries: [
        incomplete(WEEKDAY),
        incomplete(SAT_2ND),
        incomplete(HOLIDAY.event_date),
        noRecord("2026-08-21"),
      ],
    }),
    0,
  );
});

test("the card agrees with the calendar day by day", () => {
  const summaries = [
    present(SAT_2ND), // off Saturday, punched   -> Present
    present(HOLIDAY.event_date), // office closed, punched  -> Present
    present(WEEKDAY), // ordinary weekday        -> Present
    incomplete("2026-08-21"), // one punch               -> nothing
  ];
  const input = { ...emptyMonth(), events: [HOLIDAY], summaries };

  assert.deepEqual(resolveAttendanceDay({ weekend: true, summary: summaries[0] }), {
    key: "present",
    source: "biometric",
  });
  assert.deepEqual(
    resolveAttendanceDay({ officeClosed: true, summary: summaries[1] }),
    { key: "present", source: "biometric" },
  );
  assert.deepEqual(resolveAttendanceDay({ summary: summaries[2] }), {
    key: "present",
    source: "biometric",
  });
  assert.equal(resolveAttendanceDay({ summary: summaries[3] }), null);

  assert.equal(presentDaysInMonth(input), 3);
});

test("a mixed month sums records and punches into one figure", () => {
  const input = {
    year: YEAR,
    month: MONTH,
    records: [
      { attendance_date: "2026-08-03", status: "present" as const },
      { attendance_date: "2026-08-04", status: "half_day" as const },
      { attendance_date: "2026-08-05", status: "leave" as const },
      { attendance_date: "2026-08-06", status: "absent" as const },
    ],
    events: [HOLIDAY],
    summaries: [
      present("2026-08-05"), // leave record wins: adds nothing
      present("2026-08-07"), // no record at all: adds 1.0
      present(HOLIDAY.event_date), // holiday, punched: adds 1.0
      incomplete("2026-08-21"), // unsettled: adds nothing
    ],
  };
  // 1.0 (3rd) + 0.5 (4th) + 1.0 (7th) + 1.0 (17th) = 3.5
  assert.equal(presentDaysInMonth(input), 3.5);
});

test("dates outside the month are ignored", () => {
  assert.equal(
    presentDaysInMonth({
      ...emptyMonth(),
      records: [{ attendance_date: "2026-07-31", status: "present" }],
      summaries: [present("2026-09-01")],
    }),
    0,
  );
});

test("half days sum without floating-point drift", () => {
  const records = Array.from({ length: 3 }, (_, i) => ({
    attendance_date: `2026-08-${String(17 + i).padStart(2, "0")}`,
    status: "half_day" as const,
  }));
  assert.equal(presentDaysInMonth({ ...emptyMonth(), records }), 1.5);
});

// ── formatPresentDays ───────────────────────────────────────────────────────

test("whole days render without a decimal, half days keep theirs", () => {
  assert.equal(formatPresentDays(0), "0");
  assert.equal(formatPresentDays(18), "18");
  assert.equal(formatPresentDays(18.5), "18.5");
  assert.equal(formatPresentDays(0.5), "0.5");
});
