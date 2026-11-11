/**
 * Who sees deliverable management controls on the Deliverables page.
 *
 * Mirrors the backend rule (ADR-003 Amendment 2): a Project Manager manages
 * every project; an assigned Project Head manages only the projects they head.
 * This is display only - the backend re-checks every write.
 *
 * Pure and type-only imports, so it runs under `node --test`.
 */

interface ProjectLike {
  id: string;
  head_employee_id?: string | null;
}

/** Projects the caller may create deliverables on. */
export function creatableProjects<P extends ProjectLike>(
  role: string | null | undefined,
  employeeId: string | null | undefined,
  projects: readonly P[],
): P[] {
  if (role === "project_manager") return [...projects];
  if (!employeeId) return [];
  return projects.filter((p) => p.head_employee_id === employeeId);
}

/** Edit/Delete on one row: the backend's per-caller `can_manage` flag. */
export function canManageRow(d: { can_manage: boolean }): boolean {
  return d.can_manage === true;
}
