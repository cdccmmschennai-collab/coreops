/**
 * Where "Submit Pending Reports" sends the employee: the New report form with
 * the EARLIEST outstanding date prefilled, one date per click.
 *
 * Pure on purpose. The outstanding dates come from `GET /report-compliance/me`
 * (`pending_dates`), the single source of the missing-report rules - worked
 * days strictly before today with no submitted report. This module owns no
 * rule of its own: it only picks the earliest of what the server said and
 * builds the URL, so the caller must hand it a freshly fetched list.
 */

export const NEW_REPORT_PATH = "/work-reports/new";
export const REPORTS_LIST_PATH = "/work-reports";

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/**
 * A `YYYY-MM-DD` string that names a real calendar date, returned unchanged;
 * anything else is null. Checked field by field rather than via
 * `new Date(raw)` so no UTC conversion can shift the day (a `Date` parsed from an ISO date is
 * UTC midnight, which is the previous day west of Greenwich).
 *
 * This is a prefill guard only. The server still validates the date on save.
 */
export function parseReportDateParam(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const m = ISO_DATE.exec(raw);
  if (!m) return null;
  const year = Number(m[1]);
  const month = Number(m[2]);
  const day = Number(m[3]);
  if (month < 1 || month > 12 || day < 1) return null;
  // Day 0 of the next month is the last day of this one (UTC, so no DST/zone
  // edge can move it).
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
  if (day > daysInMonth) return null;
  return raw;
}

/** The earliest valid date in `pendingDates`, or null when none remain. */
export function earliestPendingDate(pendingDates: readonly string[] | null | undefined): string | null {
  let earliest: string | null = null;
  for (const d of pendingDates ?? []) {
    if (parseReportDateParam(d) === null) continue;
    // ISO dates order lexically, so a string compare is a date compare.
    if (earliest === null || d < earliest) earliest = d;
  }
  return earliest;
}

/** New report URL for the earliest pending date, or null when all are done. */
export function pendingReportPath(pendingDates: readonly string[] | null | undefined): string | null {
  const date = earliestPendingDate(pendingDates);
  return date === null ? null : `${NEW_REPORT_PATH}?date=${date}`;
}

export type PendingReportOutcome =
  /** A due date exists: open the New report form at the earliest one. */
  | { kind: "open"; path: string }
  /** Nothing is due and today has no warning either. */
  | { kind: "all_done" }
  /** Nothing is due, but today's report looks incomplete. Today is still
   *  inside its reporting window (it only becomes pending tomorrow), so this
   *  is neither overdue nor "completed" - just a reminder. */
  | { kind: "today_incomplete" };

/** What a click on "Submit Pending Reports" should do, from a fresh snapshot.
 *  Today's incomplete report never redirects anywhere: only dates the server
 *  already lists as due (strictly before today) are opened. */
export function pendingReportOutcome(
  snapshot: { pending_dates?: readonly string[] | null; fraction_mismatch_today?: boolean } | null | undefined,
): PendingReportOutcome {
  const path = pendingReportPath(snapshot?.pending_dates);
  if (path) return { kind: "open", path };
  return snapshot?.fraction_mismatch_today === true ? { kind: "today_incomplete" } : { kind: "all_done" };
}
