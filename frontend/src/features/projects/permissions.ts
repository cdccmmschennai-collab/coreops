/**
 * Per-project authority — the single client-side definition of "what may this
 * user do to THIS project".
 *
 * `lib/rbac.ts` answers role-level questions ("is this user a PM?") and cannot
 * express per-project authority, because Head is a property of one project row
 * (`project.head_employee_id`), not of the JWT role. So the two combine here,
 * and every consumer — the Edit button, the /edit page guard, the Tag Scope tab
 * — reads from this file rather than re-deriving the rule.
 *
 * Mirrors backend `app/core/authz.py`:
 *   can_edit_project    -> PM, or the employee assigned as this project's Head
 *   can_manage_project  -> PM only (create / archive / delete / assign Head)
 *
 * The API is the source of truth; this only decides what the UI offers.
 * Deliberately dependency-free so `node --test` can cover it.
 */

export interface ProjectViewer {
  /** Role-level PM: `can(role, "project.manage")`. Applies to every project. */
  canManage: boolean;
  /** This viewer's employee id equals THIS project's `head_employee_id`. */
  isHead: boolean;
}

/**
 * PM or this project's assigned Head — the "project administrator" set.
 *
 * Head authority is project-scoped by construction: `isHead` is computed
 * against the project currently on screen, so heading project A grants nothing
 * on project B. Activity Lead / Contributor / QC are activity staffing roles
 * and never reach this set.
 */
export function isProjectAdmin(viewer: ProjectViewer): boolean {
  return viewer.canManage || viewer.isHead;
}

/** Edit this project's information (PATCH /projects/{id}). */
export function canEditProject(viewer: ProjectViewer): boolean {
  return isProjectAdmin(viewer);
}

/**
 * Archive / delete the project, and assign its Head — PM only, unchanged.
 * Kept separate from `canEditProject` so widening edit access never silently
 * widens destructive actions.
 */
export function canArchiveProject(viewer: ProjectViewer): boolean {
  return viewer.canManage;
}

/** Administrative Tag Scope data — same set as edit: PM or this project's Head. */
export function canViewTagScope(viewer: ProjectViewer): boolean {
  return isProjectAdmin(viewer);
}
