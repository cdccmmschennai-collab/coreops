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

export const TAG_SCOPE_STATUS_LABEL: Record<TagScopeStatus, string> = {
  PROVISIONAL: "Provisional",
  BASELINED: "Baselined",
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
}

/**
 * What the Tag Scope tab renders. Read-only in this phase: no edit affordance,
 * and deliberately no progress, worked-tag or remaining figure — those need
 * Daily Report data this phase does not touch.
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

  return { kind: "configured", message: "", hint: "", rows };
}
