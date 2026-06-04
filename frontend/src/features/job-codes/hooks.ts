import { useQuery } from "@tanstack/react-query";
import { jobCodesApi } from "./api";
import { jobCodeKeys } from "./keys";
import type { JobCodeListParams } from "./types";

export function useJobCodes(params: JobCodeListParams = {}) {
  return useQuery({
    queryKey: jobCodeKeys.list(params),
    queryFn: () => jobCodesApi.list(params),
    staleTime: 5 * 60 * 1000, // 5 min — master data changes rarely
  });
}

/**
 * Pre-fetches all active job codes and returns them as a flat list
 * suitable for Select dropdowns. Shared cache across all callers.
 */
export function useJobCodeOptions() {
  const query = useJobCodes({ active_only: true, limit: 200 });
  const items = query.data?.items ?? [];
  const byId = new Map(items.map((j) => [j.id, j]));
  return { items, byId, isLoading: query.isLoading };
}
