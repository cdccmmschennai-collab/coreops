/**
 * Project scope classification (Phase 2).
 *
 * Mirrors the backend's projects.scope_type: does this project take part in
 * Project Tag Scope functionality at all?
 *
 *   NONE       Normal / non-tag project (TOOL DEVELOPMENT, TRAINING, INTERNAL
 *              DEVELOPMENT, ...). Every pre-existing project is this.
 *   TAG_BASED  Participates in Project Tag Scope.
 *
 * In this phase the value is *only* a label: nothing in the Daily Report,
 * benchmark, Activity Master or export paths reads it. The one thing it drives
 * is which copy the Tag Scope tab shows.
 *
 * Deliberately dependency-free (like tabs.ts) so the repo's `node --test`
 * harness can cover it without jsdom / React Testing Library.
 */

export type ProjectScopeType = "NONE" | "TAG_BASED";

/** What a project is until somebody explicitly reclassifies it. */
export const DEFAULT_PROJECT_SCOPE_TYPE: ProjectScopeType = "NONE";

/** Selector options, in the order the Project Scope dropdown renders them. */
export const PROJECT_SCOPE_TYPES = ["NONE", "TAG_BASED"] as const;

export const PROJECT_SCOPE_TYPE_LABEL: Record<ProjectScopeType, string> = {
  NONE: "Normal / Non-Tag Project",
  TAG_BASED: "Tag-Based Project",
};

/**
 * Narrow whatever the API returned to a scope type the UI knows. A value from a
 * newer backend (or a project row written before the column existed) reads as
 * NONE rather than breaking the page — the same defensive default the column
 * itself carries.
 */
export function resolveScopeType(raw: string | null | undefined): ProjectScopeType {
  return raw === "TAG_BASED" ? "TAG_BASED" : DEFAULT_PROJECT_SCOPE_TYPE;
}

/** How settled the estimate is. Absent (null) = no estimate established yet. */
export type TagScopeStatus = "PROVISIONAL" | "BASELINED";

/**
 * The one place the stored statuses become words a user reads.
 *
 * The stored values stay PROVISIONAL / BASELINED everywhere — database, API,
 * revision history. Only the wording changed, because "Baselined" was reading
 * as "frozen" when the business meaning is softer:
 *
 *   Initial Estimate  an early tag count; scope may still move as FMTL /
 *                     document / reference analysis progresses.
 *   Confirmed Scope   the count has been accepted as the working scope. Not
 *                     permanent: a later revision can take 1,200 to 1,350 and
 *                     the status stays Confirmed Scope.
 *
 * Every display site reads this map. Do not re-spell these strings inline —
 * `StatusBadge` compares against it rather than against a literal for exactly
 * that reason.
 */
export const TAG_SCOPE_STATUS_LABEL: Record<TagScopeStatus, string> = {
  PROVISIONAL: "Initial Estimate",
  BASELINED: "Confirmed Scope",
};

/** Shown wherever a scope value has not been established. Never "0" — unknown
 *  scope and a scope of zero are different business facts. */
export const NOT_SET_LABEL = "Not set";

export function resolveTagScopeStatus(
  raw: string | null | undefined,
): TagScopeStatus | null {
  return raw === "PROVISIONAL" || raw === "BASELINED" ? raw : null;
}

/** Thousands-separated, with an explicit locale so it renders identically on
 *  the server, in the browser and under `node --test`. */
export function formatTagCount(count: number | null | undefined): string {
  if (count === null || count === undefined) return NOT_SET_LABEL;
  return count.toLocaleString("en-US");
}

export interface TagScopeRow {
  label: string;
  value: string;
}

export interface TagScopeView {
  /**
   * not-tag-based — scope_type NONE: nothing to configure.
   * unconfigured  — TAG_BASED with no estimate yet (the honest NULL state).
   * configured    — TAG_BASED with an established estimate.
   */
  kind: "not-tag-based" | "unconfigured" | "configured";
  /** Headline above the rows; empty once scope exists. */
  message: string;
  /** Secondary explanatory line; empty when there is none. */
  hint: string;
  /** Read-only value rows. Empty for a non-tag project. */
  rows: TagScopeRow[];
}

export interface TagScopeInput {
  scopeType: ProjectScopeType;
  estimatedTagCount: number | null | undefined;
  tagScopeStatus: string | null | undefined;
  tagScopeRevision: number | null | undefined;
  /**
   * Audit stamp for the configured state, pre-formatted by the caller. Passed
   * in as strings (rather than an ISO date + a Date call here) so this module
   * stays dependency-free for `node --test` while the component keeps using the
   * repo's one date convention, `lib/format.ts`.
   */
  updatedAt?: string | null;
  updatedByName?: string | null;
}

/**
 * What the Tag Scope tab renders.
 *
 * Values only — the action buttons are the component's business. That split is
 * why this stayed honest through Phase 4: adding "Set" / "Revise" changed no
 * copy here, and the panel still shows no progress, worked-tag or remaining
 * figure, because those need Daily Report data this phase does not touch.
 */
export function buildTagScopeView(input: TagScopeInput): TagScopeView {
  const revision = input.tagScopeRevision ?? 0;

  if (input.scopeType !== "TAG_BASED") {
    return {
      kind: "not-tag-based",
      message: "This project is not configured as a tag-based project.",
      hint: "Change the Project Scope from the Edit Project page to enable tag-scope functionality.",
      rows: [],
    };
  }

  const status = resolveTagScopeStatus(input.tagScopeStatus);
  const configured = input.estimatedTagCount !== null && input.estimatedTagCount !== undefined;

  const rows: TagScopeRow[] = [
    { label: "Estimated Tags", value: formatTagCount(input.estimatedTagCount) },
    { label: "Status", value: status ? TAG_SCOPE_STATUS_LABEL[status] : NOT_SET_LABEL },
    { label: "Revision", value: String(revision) },
  ];

  if (!configured) {
    return {
      kind: "unconfigured",
      message: "Scope has not been configured yet.",
      hint: "This project is configured as a tag-based project.",
      rows,
    };
  }

  // Only shown once there is something to attribute. An unconfigured project
  // has no author and no timestamp, and a blank "Updated By" row would be worse
  // than no row at all.
  if (input.updatedAt) rows.push({ label: "Last Updated", value: input.updatedAt });
  if (input.updatedByName) rows.push({ label: "Updated By", value: input.updatedByName });

  return { kind: "configured", message: "", hint: "", rows };
}

// --------------------------------------------------------------------------
// Phase 4 — the managed set / revise workflow.
//
// Everything below is the client half of rules the API enforces independently
// (see backend `service.record_tag_scope_revision`). None of it is a
// substitute for the server check; it exists so the form can refuse obvious
// mistakes without a round trip, and explain them in the user's words.
// --------------------------------------------------------------------------

/** Button that opens the form: the first estimate is a "set", never a "revise". */
export function tagScopeActionLabel(kind: TagScopeView["kind"]): string {
  return kind === "configured" ? "Revise Tag Scope" : "Set Tag Scope";
}

/**
 * Strict parse of the Estimated Tag Count field, returning null for anything
 * that is not a whole positive count.
 *
 * Digits only, deliberately: `Number("2.5")`, `Number(" 1 ")` and `Number("1e3")`
 * all produce a number, and only a regex keeps "2.5" and "abc" out while "2500"
 * gets through. Zero is rejected along with negatives — an unknown scope is
 * NULL, never 0.
 */
export function parseTagCount(raw: string | null | undefined): number | null {
  const trimmed = (raw ?? "").trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const n = Number(trimmed);
  return Number.isSafeInteger(n) && n > 0 ? n : null;
}

export const TAG_COUNT_ERROR = "Enter a whole number greater than 0.";
export const REASON_REQUIRED_ERROR = "A reason is required for a scope change.";

/** The scope a project currently carries, and the scope somebody is proposing. */
export interface TagScopeValues {
  estimatedTagCount: number | null;
  status: TagScopeStatus | null;
}

/**
 * True when the proposal is the stored scope verbatim.
 *
 * Saving it must not mint a revision — history records decisions, and "someone
 * pressed Save" is not one. The UI disables Save on this; the API refuses to
 * write it regardless, so the two agree without the UI being load-bearing.
 */
export function isNoOpScopeChange(current: TagScopeValues, next: TagScopeValues): boolean {
  return (
    current.estimatedTagCount === next.estimatedTagCount && current.status === next.status
  );
}

export const NO_CHANGE_HINT = "Change the count or the status to record a revision.";

/**
 * Wording for a failed save. Shown verbatim, so a raw backend traceback, an
 * `undefined` or a bare status code can never reach the user.
 *
 * A 409 gets the documented conflict sentence rather than the server's phrasing
 * because the client also has to say what happens next (the tab refetches).
 */
export const TAG_SCOPE_CONFLICT_MESSAGE =
  "The tag scope changed while you were editing it. Refresh and review the latest scope before updating.";

export function tagScopeErrorMessage(
  status: number | null | undefined,
  message?: string | null,
): string {
  if (status === 409) return TAG_SCOPE_CONFLICT_MESSAGE;
  if (status === 403) return "You do not have permission to change this project's tag scope.";
  if (status === 404) return "This project no longer exists.";
  if (status === 0) return "Could not reach the server. Check your connection and try again.";
  const clean = (message ?? "").trim();
  // 422 carries a useful, human-written reason from the service; 500 does not.
  if (clean && status !== undefined && status !== null && status < 500) return clean;
  return "Something went wrong. Please try again.";
}

/** One row of the Scope History table, fully formatted. */
export interface TagScopeHistoryRow {
  key: string;
  revision: number;
  previous: string;
  next: string;
  status: string;
  reason: string;
  updatedBy: string;
  date: string;
}

/** What the API returns per revision (the fields this table reads). */
export interface TagScopeRevisionInput {
  id: string;
  revision: number;
  previous_estimated_tag_count: number | null;
  new_estimated_tag_count: number;
  previous_status: string | null;
  new_status: string;
  reason: string;
  changed_by_name?: string;
  created_at: string;
}

/** Shown where revision 1 has no predecessor — an em-dash-free placeholder. */
export const NO_PREVIOUS_VALUE = "-";

/**
 * Newest revision first: the current scope is what a reader is looking for, and
 * the trail behind it is context. `formatDate` is injected for the same reason
 * `updatedAt` is pre-formatted above — it keeps this module testable.
 */
export function buildTagScopeHistoryRows(
  revisions: readonly TagScopeRevisionInput[],
  formatDate: (iso: string) => string,
): TagScopeHistoryRow[] {
  return [...revisions]
    .sort((a, b) => b.revision - a.revision)
    .map((r) => {
      const status = resolveTagScopeStatus(r.new_status);
      return {
        key: r.id,
        revision: r.revision,
        previous:
          r.previous_estimated_tag_count === null
            ? NO_PREVIOUS_VALUE
            : formatTagCount(r.previous_estimated_tag_count),
        next: formatTagCount(r.new_estimated_tag_count),
        status: status ? TAG_SCOPE_STATUS_LABEL[status] : r.new_status,
        reason: r.reason,
        updatedBy: r.changed_by_name?.trim() || "Unknown",
        date: formatDate(r.created_at),
      };
    });
}
