/**
 * Display vocabulary for the PM daily review. Pure.
 *
 * No runtime imports and no `@/` alias, so the host-Node harness can load it
 * directly - the one import below is `import type`, which is erased entirely.
 *
 * NOTHING HERE CALCULATES. The backend owns first_in, last_out, worked_minutes,
 * scheduled_minutes, the classification and the reasons; this file turns those
 * into words. In particular it does not re-derive a duration, re-classify a day,
 * or decide which reasons matter - the last of those is a policy question and
 * the API answers it with `blocking_reasons`.
 */

import type { BiometricClassification } from "./day-detail";

export type { BiometricClassification };

/** The filter chips, in the order the PM sees them. */
export const REVIEW_FILTERS = [
  { value: "needs_review", label: "Needs review" },
  { value: "all", label: "All" },
  { value: "present", label: "Present" },
  { value: "incomplete", label: "Incomplete" },
  { value: "no_record", label: "No record" },
] as const;

export type ReviewFilter = (typeof REVIEW_FILTERS)[number]["value"];

/**
 * "Needs review" is the landing view on purpose.
 *
 * The screen exists to answer "show me what I need to fix", not "make me read
 * 100 normal rows". A day where everything is settled should therefore open
 * empty, which is the correct and useful answer.
 */
export const DEFAULT_REVIEW_FILTER: ReviewFilter = "needs_review";

export function isReviewFilter(value: string): value is ReviewFilter {
  return REVIEW_FILTERS.some((f) => f.value === value);
}

/** The `classification` query parameter, or undefined for "all". */
export function filterToClassification(filter: ReviewFilter): string | undefined {
  return filter === "all" ? undefined : filter;
}

export const CLASSIFICATION_LABEL: Record<BiometricClassification, string> = {
  present: "Present",
  incomplete: "Incomplete",
  needs_review: "Needs review",
  no_record: "No record",
};

/**
 * Badge variant per classification, using the design system's existing tones.
 *
 * `incomplete` and `needs_review` share `warning` deliberately: both mean "a
 * human still has to look at this", and giving them different colours would
 * suggest one of them is settled. `no_record` is neutral, not danger - an
 * absence of evidence is not yet a problem, and colouring it red would read as
 * "absent", which is exactly the conclusion this system refuses to draw.
 */
export const CLASSIFICATION_VARIANT: Record<
  BiometricClassification,
  "success" | "warning" | "neutral"
> = {
  present: "success",
  incomplete: "warning",
  needs_review: "warning",
  no_record: "neutral",
};

/**
 * Plain-English reason text.
 *
 * Written for a project manager, not for a developer: no slugs, no field names,
 * no "shift_source", and nothing that reads like an error when it is merely an
 * observation. An unmapped slug falls through to `null` rather than being shown
 * raw, so a backend addition can never leak `short_of_scheduled_duration` into
 * the UI.
 */
const REASON_TEXT: Record<string, string> = {
  no_biometric_record: "No biometric record for this day",
  missing_second_punch: "Only one punch recorded - no OUT",
  short_of_scheduled_duration: "Short of scheduled duration",
  shift_unknown: "No working hours configured",
  unsupported_shift_window: "Working hours span midnight - not supported",
  shift_timezone_invalid: "Office timezone is not valid",
  // Context-only. Present here so a curious reader gets words rather than a
  // slug, but these never appear as a review reason - the API keeps them out
  // of `blocking_reasons`.
  first_punch_after_shift_start: "Arrived after the shift start",
  last_punch_before_shift_end: "Left before the shift end",
  default_shift_assumed: "No office assigned - default hours assumed",
};

export function reasonText(slug: string): string | null {
  return REASON_TEXT[slug] ?? null;
}

/**
 * The single line shown as "Reason", or null when the day needs no attention.
 *
 * Reads only `blocking_reasons`, so context notes such as "arrived after the
 * shift start" never masquerade as a problem. The first blocking reason is the
 * decisive one - the API orders them that way.
 */
export function primaryReason(blockingReasons: string[]): string | null {
  for (const slug of blockingReasons) {
    const text = reasonText(slug);
    if (text) return text;
  }
  return null;
}

/** `480` -> `"8h 00m"`. Display only. */
export function formatWorked(minutes: number | null | undefined): string {
  if (minutes == null || minutes < 0) return EMPTY;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h}h ${String(m).padStart(2, "0")}m`;
}

/** What a value the system does not have looks like. Never a guessed time. */
export const EMPTY = "-";

/**
 * `"2026-08-14"` -> `"14 August 2026"`.
 *
 * Parsed as a plain calendar date with no zone conversion: the string is already
 * the local attendance day, and pushing it through a timezone would move it.
 */
export function formatReviewDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", {
    timeZone: "UTC",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}
