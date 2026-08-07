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

export interface TagScopePlaceholder {
  title: string;
  description: string;
}

/**
 * Copy for the Tag Scope tab, which is still a placeholder in this phase — the
 * two variants only tell the PM / Head whether the project is classified for
 * tag scope, and where to change that. No tag-count input, no enable button:
 * classification lives on the Project Edit form.
 */
export function tagScopePlaceholder(scopeType: ProjectScopeType): TagScopePlaceholder {
  if (scopeType === "TAG_BASED") {
    return {
      title: "This project is configured as a tag-based project.",
      description: "Tag scope configuration will be added in the next phase.",
    };
  }
  return {
    title: "This project is not configured as a tag-based project.",
    description:
      "Change the Project Scope from the Edit Project page to enable tag-scope functionality.",
  };
}
