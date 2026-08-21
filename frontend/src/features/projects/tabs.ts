/**
 * Tab policy for the Project Detail page.
 *
 * Kept as a pure, dependency-free module so the visibility rules can be unit
 * tested by the repo's `node --test` harness (see package.json `test:unit`),
 * which has no jsdom / React Testing Library. The component in
 * `components/project-detail.tsx` renders exactly what these helpers return —
 * it never decides tab visibility on its own.
 *
 * Visibility rules, in render order:
 *   Overview      — every user already permitted to view the project.
 *   Production
 *   Status        — PM, this project's Head, or the Lead of any activity on it
 *                   (Phase 2). Narrower than Tag Scope: a plain contributor can
 *                   open the project but not its production figures.
 *   Tag Scope     — every viewer too. The scope and its revision history are
 *                   context contributors need; only the Revise action inside
 *                   the tab is restricted to PM / this project's Head, which
 *                   the tab itself gates via canManageTagScope.
 *   Summary       — every user already permitted to view the project.
 *   Weekly Report — THIS project's assigned Head only (Phase 7). The one
 *                   restricted tab on the page, and the one place a PM is not
 *                   included; see canViewWeeklyReport for why.
 *
 * The page-level "can I see this project at all" check is unchanged and still
 * enforced by the API (GET /projects/{id} 403/404) — this module only decides
 * which tabs a viewer who already passed that check may open.
 */

// Relative .ts value import — the node --test harness resolves it directly.
import {
  canViewProductionStatus,
  canViewTagScope,
  canViewWeeklyReport,
  type ProjectViewer,
} from "./permissions.ts";

export type ProjectTabValue =
  | "overview"
  | "tag-scope"
  | "summary"
  | "production-status"
  | "weekly-report";

/** Tab shown when no tab is selected, or when the selected one is invalid. */
export const PROJECT_DEFAULT_TAB: ProjectTabValue = "overview";

/** Query-string key backing the active tab (`/projects/{id}?tab=summary`). */
export const PROJECT_TAB_PARAM = "tab";

export interface ProjectTab {
  value: ProjectTabValue;
  label: string;
}

/**
 * Who is looking at the page. Resolved once by `useProjectAuthority` and shared
 * with the Edit button and the /edit guard — see permissions.ts.
 */
export type ProjectTabViewer = ProjectViewer;

/**
 * The tab order the page renders, and the only place it is defined.
 *
 * Production Status sits immediately after Overview: it is the screen the Head
 * and the activity Leads work in daily, so it leads the project-specific tabs
 * rather than sitting behind the reference ones. Ordering is presentation only -
 * every visibility rule below is unchanged by it, and `resolveProjectTab`
 * matches on value, so existing `?tab=` links keep working.
 */
const ALL_TABS: readonly ProjectTab[] = [
  { value: "overview", label: "Overview" },
  { value: "production-status", label: "Production Status" },
  { value: "tag-scope", label: "Tag Scope" },
  { value: "summary", label: "Summary" },
  { value: "weekly-report", label: "Weekly Report" },
];

/**
 * Tabs whose visibility depends on the viewer. Everything not listed here is
 * open to every viewer who may open the project at all.
 *
 * One entry per restricted tab, each pointing at the predicate that owns the
 * rule — so restricting a tab stays a single line, and the rule itself lives
 * next to the backend check it mirrors rather than being inlined here.
 */
const RESTRICTED: Partial<Record<ProjectTabValue, (viewer: ProjectTabViewer) => boolean>> = {
  "production-status": canViewProductionStatus,
  "weekly-report": canViewWeeklyReport,
};

export function canSeeProjectTab(
  tab: ProjectTabValue,
  viewer: ProjectTabViewer,
): boolean {
  const rule = RESTRICTED[tab];
  if (rule) return rule(viewer);
  return canViewTagScope();
}

/** The tabs to render, in order, for this viewer. */
export function buildProjectTabs(viewer: ProjectTabViewer): ProjectTab[] {
  return ALL_TABS.filter((tab) => canSeeProjectTab(tab.value, viewer));
}

/**
 * Normalise whatever is in the URL into a tab this viewer is actually allowed
 * to open. Everything unrecognised falls back to Overview rather than rendering
 * a blank page — including the removed `activities` / `submissions` values from
 * bookmarked links, and a hand-typed `weekly-report` from someone who is not
 * this project's Head (so hiding the tab is not the only protection).
 */
export function resolveProjectTab(
  raw: string | null | undefined,
  viewer: ProjectTabViewer,
): ProjectTabValue {
  const match = ALL_TABS.find((tab) => tab.value === raw);
  if (!match) return PROJECT_DEFAULT_TAB;
  return canSeeProjectTab(match.value, viewer) ? match.value : PROJECT_DEFAULT_TAB;
}
