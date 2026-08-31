/**
 * Report origin - the one rule behind the "AUTO" badge.
 *
 * A report row carries `origin` (backend migration 0079): "employee" for a
 * report somebody wrote, "auto" for one the 01:00 generator produced - a
 * week-off day, or a day covered by approved leave.
 *
 * Two properties of `origin` this module deliberately relies on:
 *
 *   - It is NEVER restamped. Editing an automatic report (which reopens it to
 *     draft) leaves origin = "auto", because reconciliation matches on exactly
 *     that value. So the badge must keep showing on an edited AUTO report.
 *   - It is read-only to the client. Nothing here derives, defaults or writes
 *     an origin back; the backend stays the source of truth.
 *
 * Kept as a pure module so the rule is testable under `node --test` (see
 * package.json test:unit) without jsdom / React Testing Library, and so the
 * list and the detail page cannot disagree about what counts as automatic.
 */

/** A report as far as the origin rule is concerned. */
export interface ReportOriginRow {
  origin?: string | null;
}

/**
 * True only when the backend explicitly said the report was generated.
 *
 * Anything else - "employee", a missing field (older backend), null, or a
 * value this build does not know - is treated as not automatic. Showing no
 * badge is the safe default: it leaves an employee-authored report looking
 * exactly as it always has.
 */
export function isAutoReport(report: ReportOriginRow | null | undefined): boolean {
  return report?.origin === "auto";
}
