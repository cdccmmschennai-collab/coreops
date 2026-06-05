import { useProjects } from "@/features/projects/hooks";

/**
 * RBAC-scoped project list used to populate the task-row project selects on
 * work-report screens. Archived projects are excluded (backend rejects them).
 * Exposes job_code_id and job_code_code per project so the form can auto-fill
 * the Job Code field when a project is selected.
 */
export function useProjectOptions() {
  const query = useProjects({ q: "", status: "", limit: 100, offset: 0 });
  const all = query.data?.items ?? [];
  const items = all.filter((p) => p.status !== "archived");
  const byId = new Map(all.map((p) => [p.id, p]));
  return { items, byId, isLoading: query.isLoading };
}
