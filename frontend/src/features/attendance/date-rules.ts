/**
 * Which rules an attendance day falls under, by where it sits relative to today.
 * Pure - no imports - so the host-Node harness loads it directly.
 *
 *   past    a correction: a reason is required
 *   today   ordinary entry
 *   future  planning: status only, no check-in / check-out
 *
 * The backend enforces the same three rules (`attendance/service.py`); these
 * only let the UI say so before a save is refused. `today` is the IST date as
 * `YYYY-MM-DD` (`istTodayISO`), and ISO dates compare correctly as strings.
 */

export const FUTURE_DATE_NOTICE = "Future date - no biometric evidence yet.";

export const FUTURE_TIMES_NOTICE =
  "Times can't be entered for a future date - only the status is planned.";

export const REASON_REQUIRED_MESSAGE =
  "A reason is required when changing attendance for a past date.";

export function isPastDate(date: string, today: string): boolean {
  return date < today;
}

export function isFutureDate(date: string, today: string): boolean {
  return date > today;
}

/**
 * What the Reason box opens with when an existing record is edited.
 *
 * Empty for a past day: a correction must explain THIS change, and a reason
 * already on the row explains the previous decision - pre-filling it would let
 * the PM save the old text as the new reason. Today and the future keep the
 * stored reason, so saving them does not erase it.
 */
export function initialReason(
  date: string,
  existingNote: string | null | undefined,
  today: string,
): string {
  return isPastDate(date, today) ? "" : (existingNote ?? "");
}

/** True when saving this day would be refused for want of a reason. */
export function isReasonMissing(date: string, note: string, today: string): boolean {
  return isPastDate(date, today) && note.trim() === "";
}
