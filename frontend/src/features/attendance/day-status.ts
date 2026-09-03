/**
 * What one calendar date IS, and what it is worth on "Present this month".
 *
 * Pure and read-only. No React, no API, no `@/` alias for values - the
 * host-Node unit test loads this file directly. Nothing here writes anything:
 * no attendance record is created, updated or implied into existence, and no
 * punch is touched. Every value is derived per render from data the API
 * already returns.
 *
 * WHY THIS FILE EXISTS
 * ====================
 * The calendar grid resolved a day one way (attendance record -> declared
 * working day -> holiday -> weekend -> biometric evidence) while the
 * "Present this month" KPI counted something else entirely: rows in
 * `attendance_records` whose status happened to be `present`. A day the device
 * fully recorded, that the calendar and the day popover both showed as Present,
 * added nothing to the card until a PM opened Records and re-typed it by hand.
 *
 * The resolution itself is NOT reimplemented here. `resolveDayStatus` and
 * `buildDayDetail` in `biometric/day-detail.ts` are the same functions the
 * calendar cell and the popover call, and `classification.py` on the server is
 * still the only thing that decides whether biometric evidence settles a day.
 * This module supplies the two pieces that were previously written inline in
 * `attendance-calendar.tsx` - where the company calendar sits in the order, and
 * how a resolved day converts into a number - so the card and the grid cannot
 * answer the same question differently.
 *
 * THE PRECEDENCE (management decision, 2026-08-19)
 * ===============================================
 *   1. `attendance_records.status` - an intentional human/official ruling, and
 *      the only thing allowed to overrule the device.
 *   2. biometric `present` - a valid punch means the employee WAS here, whether
 *      or not the calendar expected the office to be open.
 *   3. a `working_day` override - the office is declared open, so the day is an
 *      ordinary working day with no status of its own.
 *   4. holiday / cdc_holiday / natural_hazard -> `holiday`.
 *   5. the office week (Sunday, 2nd and 4th Saturday) -> `weekend`.
 *   6. nothing.
 *
 * Tiers 3-5 used to sit ABOVE the device, which meant a punched 2nd Saturday,
 * holiday or hazard day read as Weekend/Holiday and was worth nothing until a
 * PM re-declared the day. It now takes no PM action at all: attendance follows
 * the evidence, and the calendar entry only decides days nobody punched.
 *
 * Only `present` is promoted. `incomplete`, `needs_review` and `no_record` mean
 * the evidence did NOT settle the day, so those days keep their calendar
 * status exactly as before - a person seen once at 09:15 on a holiday has not
 * shown they worked it.
 *
 * WHAT IT DELIBERATELY DOES NOT DO
 * ================================
 * It invents no half day. Biometric evidence carries no cause (see
 * `classification.py`, which returns only present / incomplete / needs_review /
 * no_record), so `half_day` only ever arrives from an official attendance
 * record a human entered. A short biometric day is still `present` and still
 * worth a full day, exactly as the calendar shows it.
 */
import {
  buildDayDetail,
  resolveDayStatus,
  type DaySummaryLike,
  type ResolvedDayStatus,
} from "../biometric/day-detail.ts";
import { isOffEvent, type CalendarEventType } from "../calendar/types.ts";
import { daysInMonth, isoDate, isWeekend } from "./month.ts";
import type { AttendanceStatus } from "./types";

/** The facts known about one date, before anything is decided from them. */
export interface DayFacts {
  /** The official attendance record's status, when a record exists for the
   *  date. A human's ruling; it wins over everything below. */
  recordStatus?: AttendanceStatus | null;
  /** A `working_day` calendar entry - the office is declared open, which
   *  overrides both a holiday entry and the weekend. */
  declaredWorking?: boolean;
  /** A holiday / cdc_holiday / natural_hazard entry closes the office. */
  officeClosed?: boolean;
  /** The date is a non-working day under the office week (`isWeekend`). */
  weekend?: boolean;
  /** The biometric daily-summary row for the date, when the API returned one. */
  summary?: DaySummaryLike;
}

/**
 * What the COMPANY CALENDAR alone says a day is - tiers 3 to 5 of the header's
 * precedence, consulted only for a day the device did not settle.
 *
 *   1. a declared working day - the office is open, so the day is an ordinary
 *      working day with no status of its own (it does NOT become `present`);
 *   2. an office-closing calendar entry -> `holiday`;
 *   3. the office week -> `weekend`;
 *   4. nothing.
 *
 * `holiday`, `cdc_holiday` and `natural_hazard` all resolve to the single
 * `holiday` key, unchanged: `AttendanceStatus` has no value of its own for the
 * other two, and giving them one is a separate display change. The cell still
 * prints the entry's own title beside the status, so the day says which it was.
 *
 * `declaredWorking` and `officeClosed` are read as booleans by the caller
 * exactly as the cell has always read its two title maps by truthiness.
 */
export function calendarDayStatus(facts: DayFacts): AttendanceStatus | undefined {
  if (facts.declaredWorking) return undefined;
  if (facts.officeClosed) return "holiday";
  if (facts.weekend) return "weekend";
  return undefined;
}

/**
 * The one status a date resolves to - the record, the device, or the calendar.
 *
 * The record-then-device half is the shared `resolveDayStatus`, unchanged and
 * still the same function the day popover calls. What changed here is only
 * WHERE the company calendar sits: it is now consulted after that call instead
 * of being folded into it, which is exactly what moves a punched holiday or
 * off-Saturday from Weekend/Holiday to Present.
 *
 * The calendar tier reports `source: "record"` as it always has - it is an
 * official classification of the day, not biometric evidence, and the cell's
 * "from the biometric record" hint must stay on genuinely device-settled days.
 */
export function resolveAttendanceDay(
  facts: DayFacts,
): ResolvedDayStatus<AttendanceStatus> | null {
  const settled = resolveDayStatus<AttendanceStatus>(
    facts.recordStatus ?? undefined,
    buildDayDetail(facts.summary),
  );
  if (settled) return settled;
  const calendar = calendarDayStatus(facts);
  return calendar ? { key: calendar, source: "record" } : null;
}

/**
 * What one resolved day contributes to "Present this month".
 *
 *   present   1.0   - whether the record says so or the device settled it
 *   half_day  0.5   - only ever from an official record; see the file header
 *   anything  0     - leave, holiday, weekend, absent, comp_off, unresolved
 *
 * `absent` and `comp_off` are worth nothing on a PRESENT card by definition,
 * and an unresolved day (`null`: one punch, no punch, needs review) is worth
 * nothing because the evidence did not settle it - the card must not credit a
 * day the calendar leaves blank.
 */
export function presentDayCredit(
  resolved: ResolvedDayStatus<AttendanceStatus> | null,
): number {
  if (!resolved) return 0;
  if (resolved.key === "present") return 1;
  if (resolved.key === "half_day") return 0.5;
  return 0;
}

/**
 * What one attendance record cost the LEAVE POOL, in days.
 *
 * The mirror of `leave_balances/ledger.py::leave_days_for`, and it must stay
 * one:
 *
 *   fraction stated   that fraction        1 / 0.5 / 0
 *   fraction null     `leave` -> 1, anything else -> 0
 *
 * WHY THIS IS NOT A ROW COUNT
 * ===========================
 * "Leave taken" used to be `records.filter(r => r.status === "leave").length`.
 * A count and a day total agree only while every leave is a whole day, so a
 * half-day leave - which is a `half_day` row, not a `leave` one - added nothing
 * and the card could never show a ".5" at all. It read 1d where the ledger,
 * once fixed, charges 1.5.
 *
 * `half_day` alone still means 0, deliberately: it says the employee worked half
 * a day and nothing about the other half. A company-wide half day is exactly
 * that row, and it must not be billed to anyone. Only a STATED fraction charges
 * leave.
 */
export function leaveDayCredit(record: {
  status: AttendanceStatus;
  leave_day_fraction?: number | null;
}): number {
  if (record.status !== "leave" && record.status !== "half_day") return 0;
  if (record.leave_day_fraction != null) return record.leave_day_fraction;
  return record.status === "leave" ? 1 : 0;
}

/**
 * "Leave taken" for a set of attendance rows, in days.
 *
 * Summed in halves so the total is exact: 0.5 is representable in binary, but
 * accumulating thirds of it is not, and a KPI that reads "1.4999999999999998d"
 * is worse than one that reads nothing.
 */
export function leaveDaysTaken(
  records: Iterable<{
    status: AttendanceStatus;
    leave_day_fraction?: number | null;
  }>,
): number {
  let halves = 0;
  for (const record of records) halves += leaveDayCredit(record) * 2;
  return halves / 2;
}

/** A company calendar entry, reduced to what day resolution needs from it. */
export interface CalendarDayEvent {
  event_date: string;
  title: string;
  event_type: CalendarEventType;
}

/**
 * Company calendar entries as the two date -> title maps the grid renders from.
 *
 * Office-closing entries and `working_day` overrides are kept apart because
 * they mean opposite things and the cell prints them in different colours. The
 * title is carried (not just a flag) so the calendar can keep showing it, and
 * so both callers read the same truthiness the cell always has.
 */
export function calendarDayMaps(events: Iterable<CalendarDayEvent>): {
  off: Map<string, string>;
  working: Map<string, string>;
} {
  const off = new Map<string, string>();
  const working = new Map<string, string>();
  for (const ev of events) {
    if (isOffEvent(ev.event_type)) off.set(ev.event_date, ev.title);
    else if (ev.event_type === "working_day") working.set(ev.event_date, ev.title);
  }
  return { off, working };
}

/** Minimal shapes the month roll-up reads. Both are subsets of the API types,
 *  so the real `Attendance` / `DailySummary` rows satisfy them unchanged. */
export interface AttendanceRecordLike {
  attendance_date: string;
  status: AttendanceStatus;
}
export interface DailySummaryLike extends DaySummaryLike {
  summary_date: string;
}

export interface MonthPresenceInput {
  /** Four-digit year, and a 0-indexed month - the same pair the calendar's
   *  own view state and `monthRange` use. */
  year: number;
  month: number;
  records: Iterable<AttendanceRecordLike>;
  events: Iterable<CalendarDayEvent>;
  summaries: Iterable<DailySummaryLike>;
}

/**
 * "Present this month", in days, for one employee.
 *
 * Walks every date in the month rather than every attendance record, because
 * the whole point is that a present day need not have a record. A date with no
 * record, no calendar entry and no punches simply resolves to nothing and adds
 * nothing.
 *
 * Summed in halves, so the result is exact (0.5 has no binary rounding error)
 * and 21 present days plus 2 half days is 22, not 21.999999999999996.
 */
export function presentDaysInMonth(input: MonthPresenceInput): number {
  const byDate = new Map<string, AttendanceRecordLike>();
  for (const r of input.records) byDate.set(r.attendance_date, r);

  const summaryByDate = new Map<string, DailySummaryLike>();
  for (const s of input.summaries) summaryByDate.set(s.summary_date, s);

  const { off, working } = calendarDayMaps(input.events);

  let halves = 0;
  const total = daysInMonth(input.year, input.month);
  for (let day = 1; day <= total; day += 1) {
    const iso = isoDate(input.year, input.month, day);
    const resolved = resolveAttendanceDay({
      recordStatus: byDate.get(iso)?.status,
      declaredWorking: Boolean(working.get(iso)),
      officeClosed: Boolean(off.get(iso)),
      weekend: isWeekend(input.year, input.month, day),
      summary: summaryByDate.get(iso),
    });
    halves += presentDayCredit(resolved) * 2;
  }
  return halves / 2;
}

/** `18` -> `"18"`, `18.5` -> `"18.5"`. A whole number never renders as
 *  "18.0", and a half day is never rounded away into "18" or "19". */
export function formatPresentDays(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}
