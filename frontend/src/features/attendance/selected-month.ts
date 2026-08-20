/**
 * The ONE month the Attendance page is looking at.
 *
 * Pure string/integer arithmetic, no React and no API - the host-Node unit test
 * loads this file directly, which is the only way a rule in this repo gets
 * asserted on (there is no DOM harness).
 *
 * WHY A MODULE FOR THIS
 * ====================
 * The calendar owned a private `{y, m}` while the KPI cards read `nowInIST()`,
 * so the tiles described September while the grid drew August. Both now read one
 * value, and it is carried in the form the APIs actually take - the first of the
 * month as `YYYY-MM-DD` - so the page hands the same string to
 * `/leave-balances/me?month=` and `/permission-requests/balance/me?month=`
 * untransformed. Converting to `{y, m}` for the grid happens here, once.
 *
 * NO Date ARITHMETIC. `new Date("2026-08-01")` parses as UTC midnight, so a
 * browser behind UTC would step to the wrong month. The only clock consulted is
 * "which month is NOW", and that reads the Chennai business calendar - the same
 * rule `permissions/types.ts` and `leave_balances/service.py` apply, so the page
 * and the server agree on the month boundary at 00:30 IST.
 */
import { MONTHS } from "./month.ts";

const MONTH_RE = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/;

const MONTH_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
] as const;

/** A month as the calendar grid wants it: `m` is 0-indexed, like `Date`. */
export interface MonthView {
  y: number;
  m: number;
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** `(2026, 7)` -> `"2026-08-01"`. `m` is 0-indexed. */
export function monthKey(y: number, m: number): string {
  // Absolute months, so a caller passing m = 12 or m = -1 rolls the year rather
  // than producing "2026-13-01". `prevMonth`/`nextMonth` in month.ts already
  // normalise, but a hand-typed URL does not.
  const total = y * 12 + m;
  return `${String(Math.floor(total / 12)).padStart(4, "0")}-${pad((total % 12) + 1)}-01`;
}

/** `"2026-08-01"` (or any date in the month) -> `{ y: 2026, m: 7 }`; null if it
 *  is not a date at all. */
export function parseMonthKey(value: string): MonthView | null {
  const match = MONTH_RE.exec(value);
  if (!match) return null;
  const y = Number(match[1]);
  const m = Number(match[2]) - 1;
  if (m < 0 || m > 11) return null;
  return { y, m };
}

/** The first of the month containing `value`. */
export function monthKeyStart(value: string): string | null {
  const view = parseMonthKey(value);
  return view ? monthKey(view.y, view.m) : null;
}

/** The current month on the Chennai business calendar, as `YYYY-MM-01`.
 *
 *  en-CA formats as YYYY-MM-DD, which compares correctly as a plain string -
 *  same helper and same reason as `permissions/types.ts#businessToday`. */
export function businessMonthKey(
  now: Date = new Date(),
  timeZone = "Asia/Kolkata",
): string {
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
  return monthKeyStart(today) ?? today;
}

/** A month key from an untrusted source (the URL), or `fallback`.
 *
 *  A hand-typed `?att_month=banana` must not put the page into a state where
 *  every query asks the server for nonsense - it falls back to the current
 *  month, which is where the page opens anyway. */
export function normalizeMonthKey(value: string, fallback: string): string {
  return monthKeyStart(value) ?? fallback;
}

/** `delta` months away, rolling the year over correctly. */
export function shiftMonthKey(value: string, delta: number): string {
  const view = parseMonthKey(value);
  if (!view) return value;
  return monthKey(view.y, view.m + delta);
}

/** `"August 2026"` - the calendar heading and the PM table caption. */
export function monthKeyLabel(value: string): string {
  const view = parseMonthKey(value);
  if (!view) return value;
  return `${MONTHS[view.m]} ${view.y}`;
}

/** `"Aug 2026"` - the compact form appended to a KPI label. */
export function shortMonthLabel(value: string): string {
  const view = parseMonthKey(value);
  if (!view) return value;
  return `${MONTH_SHORT[view.m]} ${view.y}`;
}

/** Whether `value` is the month running now. Both arguments are month keys, so
 *  this is a string comparison and no clock is consulted. */
export function isCurrentMonthKey(value: string, currentKey: string): boolean {
  return monthKeyStart(value) === monthKeyStart(currentKey);
}

/** Whether `value`'s month has finished. A future month is NOT past - filing
 *  ahead has always been allowed, and `permissions/balance.py#month_has_closed`
 *  draws the same line on the server. */
export function isPastMonthKey(value: string, currentKey: string): boolean {
  const a = monthKeyStart(value);
  const b = monthKeyStart(currentKey);
  if (!a || !b) return false;
  return a < b;
}

/**
 * A KPI label that states its month whenever that month is not the current one.
 *
 * "Leave taken" is unambiguous while the page shows this month and actively
 * misleading while it shows August, which is the whole reason the tiles were
 * wrong before. The current month keeps the exact wording it has always had, so
 * nothing changes for the case that was already right.
 */
export function withMonth(
  base: string,
  monthValue: string,
  currentKey: string,
): string {
  if (isCurrentMonthKey(monthValue, currentKey)) return base;
  return `${base} · ${shortMonthLabel(monthValue)}`;
}
