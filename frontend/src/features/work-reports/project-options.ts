import { useProjects } from "@/features/projects/hooks";

/**
 * RBAC-scoped project list used to resolve names + populate the task-row selects
 * on the work-report screens. Mirrors `useEmployeeOptions`. Archived projects are
 * filtered out (the backend rejects tasks against non-active projects), while
 * `byId` keeps every project so existing reports referencing an archived project
 * still render its name. Shares the TanStack Query cache with other callers.
 */
export function useProjectOptions() {
  const query = useProjects({ q: "", status: "", limit: 100, offset: 0 });
  const all = query.data?.items ?? [];
  const items = all.filter((p) => p.status !== "archived");
  const byId = new Map(all.map((p) => [p.id, p.name]));
  return { items, byId, isLoading: query.isLoading };
}
