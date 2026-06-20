import { useQuery } from "@tanstack/react-query";
import { activityTypesApi } from "./api";
import { activityTypeKeys } from "./keys";
import type { ActivityTypeListParams } from "./types";

export function useActivityTypes(params: ActivityTypeListParams = {}) {
  return useQuery({
    queryKey: activityTypeKeys.list(params),
    queryFn: () => activityTypesApi.list(params),
    staleTime: 5 * 60 * 1000,
  });
}

export function useActivityTypeOptions() {
  const query = useActivityTypes({ active_only: true, limit: 200 });
  const items = query.data?.items ?? [];
  const byId = new Map(items.map((a) => [a.id, a]));
  return { items, byId, isLoading: query.isLoading };
}
