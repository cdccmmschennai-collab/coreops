/**
 * Tab policy for the Project Detail page.
 *
 * Kept as a pure, dependency-free module so the visibility rules can be unit
 * tested by the repo's `node --test` harness (see package.json `test:unit`),
 * which has no jsdom / React Testing Library. The component in
 * `components/project-detail.tsx` renders exactly what these helpers return —
 * it never decides tab visibility on its own.
 *
 * Visibility rules (Phase 1):
 *   Overview   — every user already permitted to view the project.
 *   Tag Scope  — Project Manager (system capability `project.manage`) or the
 *                project's assigned Head only.
 *   Summary    — every user already permitted to view the project.
 *
 * The page-level "can I see this project at all" check is unchanged and still
 * enforced by the API (GET /projects/{id} 403/404) — this module only decides
 * which tabs a viewer who already passed that check may open.
 */

export type ProjectTabValue = "overview" | "tag-scope" | "summary";

/** Tab shown when no tab is selected, or when the selected one is invalid. */
export const PROJECT_DEFAULT_TAB: ProjectTabValue = "overview";

/** Query-string key backing the active tab (`/projects/{id}?tab=summary`). */
export const PROJECT_TAB_PARAM = "tab";

export interface ProjectTab {
  value: ProjectTabValue;
  label: string;
}

/**
 * Who is looking at the page. Both flags come from helpers that already exist:
 *   canManage — `can(role, "project.manage")` (lib/rbac), i.e. Project Manager.
 *   isHead    — the viewer's employee id equals `project.head_employee_id`,
 *               the same comparison ProjectMembers uses for Head authority.
 */
export interface ProjectTabViewer {
  canManage: boolean;
  isHead: boolean;
}

const ALL_TABS: readonly ProjectTab[] = [
  { value: "overview", label: "Overview" },
  { value: "tag-scope", label: "Tag Scope" },
  { value: "summary", label: "Summary" },
];

/** Tabs restricted to PM / Head. Everything not listed is open to all viewers. */
const MANAGER_ONLY: readonly ProjectTabValue[] = ["tag-scope"];

export function canSeeProjectTab(
  tab: ProjectTabValue,
  viewer: ProjectTabViewer,
): boolean {
  if (!MANAGER_ONLY.includes(tab)) return true;
  return viewer.canManage || viewer.isHead;
}

/** The tabs to render, in order, for this viewer. */
export function buildProjectTabs(viewer: ProjectTabViewer): ProjectTab[] {
  return ALL_TABS.filter((tab) => canSeeProjectTab(tab.value, viewer));
}

/**
 * Normalise whatever is in the URL into a tab this viewer is actually allowed
 * to open. Everything unrecognised falls back to Overview rather than rendering
 * a blank page — including the removed `activities` / `submissions` values from
 * bookmarked links, and `tag-scope` typed in by a viewer who is neither PM nor
 * Head (so hiding the tab is not the only protection).
 */
export function resolveProjectTab(
  raw: string | null | undefined,
  viewer: ProjectTabViewer,
): ProjectTabValue {
  const match = ALL_TABS.find((tab) => tab.value === raw);
  if (!match) return PROJECT_DEFAULT_TAB;
  return canSeeProjectTab(match.value, viewer) ? match.value : PROJECT_DEFAULT_TAB;
}
