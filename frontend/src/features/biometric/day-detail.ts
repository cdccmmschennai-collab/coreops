/**
 * Display logic for the attendance day popover. Pure, read-only.
 *
 * No imports, no React, no `@/` alias - the host-Node unit test loads this file
 * directly. Nothing here writes anything, calls an API, or re-derives a boundary:
 * `first_in` and `last_out` arrive already decided by the Phase 6 backend rule
 * and are passed through untouched.
 *
 * Total hours is computed here for DISPLAY only and dies with the render. Session
 * pairing, breaks, overtime and payable hours belong to a later phase.
 */

/**
 * The three completeness states the biometric data can support.
 *
 * Used only when the day has NO official attendance record. When a record exists
 * its own status wins, because that is the authoritative word for the day and
 * biometric observation must not overrule it.
 */
export type BiometricDayStatus = "complete" | "partial" | "no_record";

export const STATUS_LABEL: Record<BiometricDayStatus, string> = {
  complete: "Present",
  // One surviving punch: seen, but the day cannot be closed out.
  partial: "Partial",
  no_record: "No biometric record",
};

/** Minimal shape needed here - a subset of the API's DailySummary. */
export interface DaySummaryLike {
  first_in: string | null;
  last_out: string | null;
}

export interface DayDetail {
  status: BiometricDayStatus;
  firstIn: string | null;
  lastOut: string | null;
  /** Display only. Null unless BOTH boundaries exist. Never persisted. */
  totalMinutes: number | null;
}

/**
 * Turn one daily-summary row (or its absence) into the popover's four values.
 *
 * `undefined` means the API returned no row for that date, which is exactly how
 * "no biometric record" is represented - a day with no punches has no row.
 */
export function buildDayDetail(summary: DaySummaryLike | undefined): DayDetail {
  if (!summary || !summary.first_in) {
    return { status: "no_record", firstIn: null, lastOut: null, totalMinutes: null };
  }
  // An OUT exists only when the backend found a second surviving punch. The UI
  // never re-derives it and never falls back to first_in.
  const complete = summary.last_out !== null;
  return {
    status: complete ? "complete" : "partial",
    firstIn: summary.first_in,
    lastOut: summary.last_out,
    totalMinutes: complete ? minutesBetween(summary.first_in, summary.last_out) : null,
  };
}

/**
 * The one line shown at the bottom: `"Present · 8h 00m"`.
 *
 * `attendanceLabel` is the official record's status when the day has one; it wins
 * over the biometric label. The duration is appended only when both boundaries
 * exist, so an incomplete day reads as a bare status rather than "· -".
 */
export function statusLine(
  detail: DayDetail,
  attendanceLabel?: string | null,
): string {
  const label = attendanceLabel ?? STATUS_LABEL[detail.status];
  if (detail.totalMinutes == null) return label;
  return `${label} · ${formatDuration(detail.totalMinutes)}`;
}

/**
 * Whole minutes between two ISO instants, or null if either is unusable.
 *
 * Returns null rather than 0 for a negative span: the backend cannot produce one
 * (last_out is drawn from a sorted list), so a negative result means something is
 * wrong and showing "0h 00m" would hide it.
 */
export function minutesBetween(
  fromIso: string | null | undefined,
  toIso: string | null | undefined,
): number | null {
  if (!fromIso || !toIso) return null;
  const a = Date.parse(fromIso);
  const b = Date.parse(toIso);
  if (Number.isNaN(a) || Number.isNaN(b) || b < a) return null;
  return Math.floor((b - a) / 60000);
}

/** `480` -> `"8h 00m"`. Display only - this is never a stored duration. */
export function formatDuration(minutes: number | null | undefined): string {
  if (minutes == null || minutes < 0) return EMPTY_VALUE;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h}h ${String(m).padStart(2, "0")}m`;
}

/** What a missing value looks like. Never a guessed time. */
export const EMPTY_VALUE = "-";

/**
 * An office `shift_start` / `shift_end` (`"09:30:00"`) as `"09:30"`.
 *
 * These are plain local TIME values with no date and no zone, so they are read as
 * digits and never pushed through a timezone conversion - doing that would shift a
 * contracted 09:30 by whatever offset the runtime guessed.
 */
export function formatShiftTime(value: string | null | undefined): string {
  if (!value) return EMPTY_VALUE;
  const match = /^(\d{1,2}):(\d{2})/.exec(value.trim());
  if (!match) return EMPTY_VALUE;
  const hours = Number(match[1]);
  const minutes = match[2];
  if (hours > 23 || Number(minutes) > 59) return EMPTY_VALUE;
  return `${String(hours).padStart(2, "0")}:${minutes}`;
}

/** `"09:00:00"`, `"17:30:00"` -> `"09:00 - 17:30"`. */
export function formatShiftWindow(
  start: string | null | undefined,
  end: string | null | undefined,
): string | null {
  const from = formatShiftTime(start);
  const to = formatShiftTime(end);
  if (from === EMPTY_VALUE || to === EMPTY_VALUE) return null;
  return `${from} - ${to}`;
}
