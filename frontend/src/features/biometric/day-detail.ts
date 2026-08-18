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
  /** "device" | "pm" | null - which value first_in/last_out came from. See
   *  the backend's `_merge_boundary`. Never affects `classification` below. */
  first_in_source?: "device" | "pm" | null;
  last_out_source?: "device" | "pm" | null;
  worked_minutes: number | null;
  scheduled_minutes: number | null;
  classification: BiometricClassification;
  review_required: boolean;
  /** Phase 12. APPROVED permission hours (1 or 2) held for this date, or null.
   *  An additional attendance ATTRIBUTE joined from `permission_requests` - it
   *  is not a status, not a leave, and it never alters the biometric fields
   *  above. Pending, rejected and cancelled requests never appear here. */
  permission_hours?: number | null;
}

export interface DayDetail {
  classification: BiometricClassification;
  firstIn: string | null;
  lastOut: string | null;
  firstInSource: "device" | "pm" | null;
  lastOutSource: "device" | "pm" | null;
  /** Elapsed minutes as computed by the backend. Null when not measurable. */
  workedMinutes: number | null;
  /** The contracted window's length, for the side-by-side comparison. */
  scheduledMinutes: number | null;
  reviewRequired: boolean;
  /** Approved permission hours for the day, or null. Presentation only. */
  permissionHours: number | null;
}

/**
 * One daily-summary row (or its absence) as the popover's values.
 *
 * `undefined` means the API returned no row for that date - genuinely nothing
 * to show (no punch, no PM decision either). A day the PM HAS decided (Phase
 * 9C) always has a row, even with zero punches, so `firstIn`/`lastOut` below
 * are the FINALIZED result - device evidence first, a PM-entered time only
 * where the device recorded none - while `classification` stays evidence-only
 * and un-merged: a PM-decided Present day can still be biometrically
 * `no_record`, exactly as the Records screen shows it.
 */
export function buildDayDetail(summary: DaySummaryLike | undefined): DayDetail {
  if (!summary || !summary.first_in) {
    // A missing (or first_in-less) row is unambiguously no_record and needs
    // review, regardless of anything else a caller's fixture might claim -
    // the same defensive rule this branch has always enforced.
    return {
      classification: "no_record",
      firstIn: null,
      lastOut: null,
      firstInSource: null,
      lastOutSource: null,
      workedMinutes: null,
      scheduledMinutes: summary?.scheduled_minutes ?? null,
      reviewRequired: true,
      // Carried through even here. An approved permission is a fact about the
      // DATE, not about the punches: a day with no biometric record can still
      // hold one, and hiding it would make the employee think it was lost.
      // Nothing is invented in exchange - the times above stay null.
      permissionHours: summary?.permission_hours ?? null,
    };
  }
  return {
    classification: summary.classification,
    firstIn: summary.first_in,
    // An OUT exists only when the backend found a second surviving punch OR a
    // PM entered one. The UI never re-derives it and never falls back to
    // first_in or to the shift end.
    lastOut: summary.last_out,
    firstInSource: summary.first_in_source ?? null,
    lastOutSource: summary.last_out_source ?? null,
    workedMinutes: summary.worked_minutes,
    scheduledMinutes: summary.scheduled_minutes,
    reviewRequired: summary.review_required,
    permissionHours: summary.permission_hours ?? null,
  };
}

/** Where the status a day is displayed with actually came from. */
export type DayStatusSource = "record" | "biometric";

export interface ResolvedDayStatus<K extends string = string> {
  /** The status key to render with - an attendance status, never a slug of its
   *  own, so a caller's existing colour/label table covers it unchanged. */
  key: K;
  source: DayStatusSource;
}

/**
 * The ONE status a day resolves to, for every surface that shows that day.
 *
 * This exists because the calendar grid and the day popover were answering
 * "what is this day?" separately: the cell read only the official attendance
 * record, while the popover fell back to the biometric classification when no
 * record existed. A fully-punched day nobody had ruled on therefore rendered as
 * a BLANK cell that opened a panel reading "Present · 8h 44m". Both now call
 * this, so the grid cannot disagree with the panel it opens.
 *
 * Precedence, and why:
 *
 *   1. `officialStatus` - a human's ruling (the attendance record) or the
 *      office calendar's own derivation (holiday, weekend). It wins outright:
 *      observation never overrules the record, which is the rule the whole
 *      biometric module is built on.
 *   2. a `present` classification - the device saw BOTH ends of the day, so the
 *      evidence is complete and settles it on its own.
 *   3. nothing.
 *
 * `incomplete`, `needs_review` and `no_record` deliberately resolve to nothing.
 * Each of those means the evidence did NOT settle the day, and promoting one to
 * a status would be exactly the invented cause `classification.py` refuses to
 * produce - a one-punch day is a person seen once, not a person present.
 */
export function resolveDayStatus<K extends string>(
  officialStatus: K | null | undefined,
  detail: DayDetail,
): ResolvedDayStatus<K | "present"> | null {
  if (officialStatus) return { key: officialStatus, source: "record" };
  if (detail.classification === "present") {
    return { key: "present", source: "biometric" };
  }
  return null;
}

/**
 * `2` -> `"2hr"`. Null when there is no approved permission for the day.
 *
 * `hr` singular for both 1 and 2, because that is the company's own shorthand -
 * "1hr", "2hr" - and it is what Phase 11's request UI already says.
 *
 * Only ever reached with an APPROVED value: pending, rejected and cancelled
 * requests are filtered out server-side and never arrive here at all.
 */
export function formatPermission(hours: number | null | undefined): string | null {
  if (hours == null || !Number.isFinite(hours) || hours <= 0) return null;
  return `${hours}hr`;
}

/**
 * `"Present"` + 2 -> `"Present | 2hr"`.
 *
 * The permission is APPENDED, never substituted: the day's own status is still
 * the first thing read, and a permission does not become an attendance status
 * of its own. With no permission the label comes back untouched, so every
 * existing day renders exactly as it did.
 *
 * With no status label at all (a day nobody has ruled on) it reads
 * `"Permission 2hr"` rather than a bare `"| 2hr"` - a suffix with nothing in
 * front of it is not a sentence, and the hours must still be visible.
 */
export function statusWithPermission(
  label: string | null | undefined,
  hours: number | null | undefined,
): string | null {
  const permission = formatPermission(hours);
  if (!label) return permission ? `Permission ${permission}` : null;
  return permission ? `${label} | ${permission}` : label;
}

/**
 * The one line shown at the bottom: `"Present · 8h 30m"`, or with an approved
 * permission `"Present | 2hr · 16h 17m"`.
 *
 * `attendanceLabel` is the official record's status when the day has one; it wins
 * over the biometric label, because the record is the authoritative word for the
 * day and observation must not overrule it. The duration is appended only when it
 * was measurable, so an incomplete day reads as a bare status rather than "· -".
 *
 * Phase 12: the permission sits between the status and the duration, because it
 * qualifies the STATUS ("present, with two sanctioned hours") rather than the
 * measurement. The duration stays the biometric worked total, untouched - a 2hr
 * permission does not shorten `16h 17m`.
 */
export function statusLine(
  detail: DayDetail,
  attendanceLabel?: string | null,
): string {
  const label = attendanceLabel ?? CLASSIFICATION_LABEL[detail.classification];
  const head = statusWithPermission(label, detail.permissionHours) ?? label;
  if (detail.workedMinutes == null) return head;
  return `${head} · ${formatDuration(detail.workedMinutes)}`;
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
 * An office `shift_start` / `shift_end` (`"09:30:00"`) as `"09:30 AM"`.
 *
 * These are plain local TIME values with no date and no zone, so they are read as
 * digits and never pushed through a timezone conversion - doing that would shift a
 * contracted 09:30 by whatever offset the runtime guessed.
 *
 * Rendered on the 12-hour clock like every other time in CoreOps (2026-08-18);
 * the same conversion `mapping-format.to12Hour` performs, restated here only
 * because this file is deliberately import-free for the host-Node harness.
 */
export function formatShiftTime(value: string | null | undefined): string {
  if (!value) return EMPTY_VALUE;
  const match = /^(\d{1,2}):(\d{2})/.exec(value.trim());
  if (!match) return EMPTY_VALUE;
  const hours = Number(match[1]);
  const minutes = match[2];
  if (hours > 23 || Number(minutes) > 59) return EMPTY_VALUE;
  const period = hours < 12 ? "AM" : "PM";
  const h12 = hours % 12 === 0 ? 12 : hours % 12;
  return `${String(h12).padStart(2, "0")}:${minutes} ${period}`;
}

/** `"09:00:00"`, `"17:30:00"` -> `"09:00 AM - 05:30 PM"`. */
export function formatShiftWindow(
  start: string | null | undefined,
  end: string | null | undefined,
): string | null {
  const from = formatShiftTime(start);
  const to = formatShiftTime(end);
  if (from === EMPTY_VALUE || to === EMPTY_VALUE) return null;
  return `${from} - ${to}`;
}
