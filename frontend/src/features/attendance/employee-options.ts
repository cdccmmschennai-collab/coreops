import { useEmployees } from "@/features/employees/hooks";

/**
 * RBAC-scoped employee list used to resolve names + populate selects on the
 * attendance screens. Shares the TanStack Query cache with other callers.
 */
export function useEmployeeOptions() {
  const query = useEmployees({
    q: "",
    status: "",
    department: "",
    manager_id: "",
    limit: 100,
    offset: 0,
  });
  const items = query.data?.items ?? [];
  const byId = new Map(items.map((e) => [e.id, e.full_name]));
  return { items, byId, isLoading: query.isLoading };
}
