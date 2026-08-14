/**
 * Display logic for the attendance day popover. Pure, read-only.
 *
 * No imports, no React, no `@/` alias - the host-Node unit test loads this file
 * directly. Nothing here writes anything or calls an API.
 *
 * IT ALSO DECIDES NOTHING. Since Phase 7 the classification and the worked
 * duration arrive already computed by the backend (`classification.py`) and are
 * passed straight through. The frontend deliberately owns no second copy of the
 * duration rule: two implementations of "how long was this person here" would
 * eventually disagree, and the one the user sees would be the wrong one. What is
 * left here is formatting and label lookup.
 */

/**
 * The four things biometric evidence can support.
 *
 * Mirrors the backend vocabulary exactly. Note what is NOT here: half day,
 * permission, leave, absent. Those encode a CAUSE, and a punch stream has none -
 * a short day means "we measured 6 hours", never "HR decided half day".
 */
export type BiometricClassification =
  | "present"
  | "incomplete"
  | "needs_review"
  | "no_record";

export const CLASSIFICATION_LABEL: Record<BiometricClassification, string> = {
  present: "Present",
  // One surviving punch: seen, but the day cannot be closed out.
  incomplete: "Incomplete",
  // Measurable, but not objectively settled - a human decides.
  needs_review: "Needs review",
  no_record: "No biometric record",
};

/** Minimal shape needed here - a subset of the API's DailySummary. */
export interface DaySummaryLike {
  first_in: string | null;
  last_out: string | null;
  worked_minutes: number | null;
  scheduled_minutes: number | null;
  classification: BiometricClassification;
  review_required: boolean;
}

export interface DayDetail {
  classification: BiometricClassification;
  firstIn: string | null;
  lastOut: string | null;
  /** Elapsed minutes as computed by the backend. Null when not measurable. */
  workedMinutes: number | null;
  /** The contracted window's length, for the side-by-side comparison. */
  scheduledMinutes: number | null;
  reviewRequired: boolean;
}

/**
 * One daily-summary row (or its absence) as the popover's values.
 *
 * `undefined` means the API returned no row for that date, which is exactly how
 * "no biometric record" is represented - a day with no punches has no row. That
 * is an absence of evidence, so it is `no_record` and flagged for review; it is
 * never presented as an absence from work.
 */
export function buildDayDetail(summary: DaySummaryLike | undefined): DayDetail {
  if (!summary || !summary.first_in) {
    return {
      classification: "no_record",
      firstIn: null,
      lastOut: null,
      workedMinutes: null,
      scheduledMinutes: summary?.scheduled_minutes ?? null,
      reviewRequired: true,
    };
  }
  return {
    classification: summary.classification,
    firstIn: summary.first_in,
    // An OUT exists only when the backend found a second surviving punch. The UI
    // never re-derives it and never falls back to first_in or to the shift end.
    lastOut: summary.last_out,
    workedMinutes: summary.worked_minutes,
    scheduledMinutes: summary.scheduled_minutes,
    reviewRequired: summary.review_required,
  };
}

/**
 * The one line shown at the bottom: `"Present · 8h 30m"`.
 *
 * `attendanceLabel` is the official record's status when the day has one; it wins
 * over the biometric label, because the record is the authoritative word for the
 * day and observation must not overrule it. The duration is appended only when it
 * was measurable, so an incomplete day reads as a bare status rather than "· -".
 */
export function statusLine(
  detail: DayDetail,
  attendanceLabel?: string | null,
): string {
  const label = attendanceLabel ?? CLASSIFICATION_LABEL[detail.classification];
  if (detail.workedMinutes == null) return label;
  return `${label} · ${formatDuration(detail.workedMinutes)}`;
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
