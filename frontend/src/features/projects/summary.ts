/**
 * Project Summary presentation logic (Phase 6).
 *
 * Everything the Summary tab decides — which rows to show, what the search
 * matches, which empty state applies, and the exact string in every cell — is
 * decided here, and the component only renders the result. That split is what
 * makes the tab testable: the repo's `node --test` harness has no jsdom or
 * React Testing Library, so logic that lives inside JSX cannot be covered at
 * all. Anything with a rule attached belongs in this file.
 *
 * The rows themselves are computed server-side (see backend
 * `projects/tag_progress.py`). This module never does tag arithmetic: reported,
 * scope and remaining all arrive as finished integers, because the one number
 * the Summary shows must be the same number the tag cap enforces. Deriving
 * "remaining" here would create a second, drifting definition of it.
 *
 * Deliberately dependency-free (like scope.ts and tabs.ts) so `node --test` can
 * cover it without a bundler.
 */

/** One tag-counted sub-activity's progress, as the API returns it. */
export interface SummaryProgressRow {
  /** Parent Activity. Null only when master data has a parentless leaf. */
  activity_id?: string | null;
  activity_name?: string | null;
  sub_activity_id: string;
  sub_activity_name: string;
  reported_tags: number;
  estimated_tag_count: number;
  remaining_tags: number;
}

/** The Summary payload's project-level fields (the shape the states read). */
export interface SummaryPayload {
  scope_type?: string | null;
  estimated_tag_count?: number | null;
  tag_progress?: SummaryProgressRow[] | null;
}

export const SUMMARY_SEARCH_PLACEHOLDER = "Search activity or sub-activity...";

export const SUMMARY_NO_MATCH_TITLE = "No matching activities or sub-activities found.";
export const SUMMARY_NO_MATCH_HINT = "Clear the search to see all activities again.";

/**
 * Stands in for a value that is not a usable number.
 *
 * A plain hyphen, never an empty string: a blank cell reads as "this row has no
 * Remaining", which is exactly the confusion that made the original bug hard to
 * spot. A visible placeholder says "no value arrived" out loud.
 */
export const VALUE_UNAVAILABLE = "-";

/** Shown in the Activity column when a sub-activity has no parent row. */
export const ACTIVITY_UNKNOWN = VALUE_UNAVAILABLE;

/**
 * Format a whole count for display, or the placeholder when it is not a real
 * number.
 *
 * This function is the reason a Remaining cell can never come out blank. It is
 * total: null, undefined, NaN, Infinity and a non-numeric value all map to
 * VALUE_UNAVAILABLE, and every other input maps to a non-empty digit string. It
 * has no branch that returns "" and none that returns undefined, so there is no
 * input for which a caller renders nothing.
 *
 * An explicit locale so the output is identical in the browser, in a server
 * render and under `node --test`.
 */
export function formatCount(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return VALUE_UNAVAILABLE;
  return Math.trunc(value).toLocaleString("en-US");
}

/** "700 / 1,200" — reported against the scope it is measured against. */
export function formatReportedOfScope(reported: unknown, scope: unknown): string {
  return `${formatCount(reported)} / ${formatCount(scope)}`;
}

/** One fully formatted table row. Every field is a non-empty string. */
export interface SummaryTableRow {
  /** React key. The stable sub-activity id, never a name — names change. */
  key: string;
  activityId: string | null;
  activityName: string;
  subActivityId: string;
  subActivityName: string;
  /** "700 / 1,200" */
  reportedOfScope: string;
  /** "500" — never blank, never negative. */
  remaining: string;
  /**
   * True when history holds more tags than the current estimate (a scope
   * reduced below work already recorded). Remaining honestly reads 0, and the
   * flag lets the tab say why instead of leaving a confusing 0 unexplained.
   * Historical counts are never rewritten to make this go away.
   */
  overReported: boolean;
}

export const OVER_REPORTED_LABEL = "Over scope";
export const OVER_REPORTED_HINT =
  "More tags have been reported than the current estimated scope. The estimate was reduced after the work was recorded; no counts were changed.";

/**
 * Format the API rows for the table.
 *
 * `remaining_tags` is taken from the server as-is rather than recomputed from
 * scope - reported. The server already floors it at zero and is the same source
 * the cap enforces; recomputing here would be a second definition that could
 * disagree with the cap, which is the one thing the Summary must never do.
 */
export function buildSummaryRows(
  rows: readonly SummaryProgressRow[] | null | undefined,
): SummaryTableRow[] {
  return (rows ?? []).map((r) => ({
    key: r.sub_activity_id,
    activityId: r.activity_id ?? null,
    activityName: r.activity_name?.trim() || ACTIVITY_UNKNOWN,
    subActivityId: r.sub_activity_id,
    subActivityName: r.sub_activity_name?.trim() || VALUE_UNAVAILABLE,
    reportedOfScope: formatReportedOfScope(r.reported_tags, r.estimated_tag_count),
    remaining: formatCount(r.remaining_tags),
    overReported:
      typeof r.reported_tags === "number" &&
      typeof r.estimated_tag_count === "number" &&
      r.reported_tags > r.estimated_tag_count,
  }));
}

/**
 * Does this row match what was typed?
 *
 * Case-insensitive substring against the Activity name OR the Sub-Activity
 * name, so "mtl" finds both the MTL activity's rows and any sub-activity whose
 * text contains MTL, and "rework" finds DEMOLITION-REWORK without the user
 * having to know its parent. Matching the formatted strings (not the raw API
 * fields) means what is searched is exactly what is on screen.
 */
export function matchesSummaryQuery(row: SummaryTableRow, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return (
    row.activityName.toLowerCase().includes(needle) ||
    row.subActivityName.toLowerCase().includes(needle)
  );
}

/**
 * Client-side filter over the project's own progress rows.
 *
 * A project reports on a handful of tag sub-activities, all of which are
 * already in the payload the tab fetched — so a search endpoint would add a
 * round trip, a loading state and a second definition of "matches" to filter a
 * list that is already in memory. An empty or whitespace-only query returns
 * every row, which is what makes clearing the box restore the table instantly
 * with no refetch.
 */
export function filterSummaryRows(
  rows: readonly SummaryTableRow[],
  query: string,
): SummaryTableRow[] {
  return rows.filter((r) => matchesSummaryQuery(r, query));
}

/**
 * Which of the mutually exclusive states the tab is in.
 *
 *   table            — there are rows to show.
 *   not-tag-based    — a normal project; tag scope does not apply to it.
 *   unconfigured     — tag-based, but no estimate established yet.
 *   nothing-reported — scoped, but no tag work reported against it yet.
 *
 * The three empty states are worded apart on purpose. They are genuinely
 * different situations with different next actions (none / set a scope / report
 * work), and collapsing them into one "no data" message would tell a PM nothing
 * about which one they are looking at. None of them invents a 0 / 0 row.
 */
export type SummaryStateKind =
  | "table"
  | "not-tag-based"
  | "unconfigured"
  | "nothing-reported";

export interface SummaryState {
  kind: SummaryStateKind;
  title: string;
  description: string;
}

export const SUMMARY_STATE_COPY: Record<
  Exclude<SummaryStateKind, "table">,
  { title: string; description: string }
> = {
  "not-tag-based": {
    title: "This project does not use tag-based project scope.",
    description:
      "Change the Project Scope from the Edit Project page to track progress against an estimated tag count.",
  },
  unconfigured: {
    title: "Tag scope has not been configured for this project yet.",
    description:
      "Set the estimated tag scope on the Tag Scope tab to start tracking progress.",
  },
  "nothing-reported": {
    title: "No tag-based work has been reported for this project yet.",
    description:
      "Sub-activities appear here once tag counts are reported against them. Activities that have never been worked on this project are not listed.",
  },
};

export function resolveSummaryState(
  summary: SummaryPayload | null | undefined,
): SummaryState {
  const rows = summary?.tag_progress ?? [];
  if (rows.length > 0) return { kind: "table", title: "", description: "" };

  // Order matters: a NONE project can carry a stale estimate from before it was
  // reclassified, so scope_type is asked first.
  const kind: Exclude<SummaryStateKind, "table"> =
    summary?.scope_type !== "TAG_BASED"
      ? "not-tag-based"
      : summary?.estimated_tag_count == null
        ? "unconfigured"
        : "nothing-reported";

  return { kind, ...SUMMARY_STATE_COPY[kind] };
}

// There is deliberately no caption above the table. The independent-progression
// rule it used to spell out is still exactly how the numbers are computed (see
// backend tag_progress.py) - it is simply not narrated on screen any more. The
// columns carry it: every row shows its own "reported / <the same scope>", which
// is what tells a reader the rows are separate progressions rather than shares
// of a pool. Nothing about the calculation changed with the sentence.
