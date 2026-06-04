import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { activityTypesApi, type ActivityTypeCreateBody, type ActivityTypeUpdateBody } from "./api";
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

export function useCreateActivityType() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ActivityTypeCreateBody) => activityTypesApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: activityTypeKeys.all }),
  });
}

export function useUpdateActivityType(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ActivityTypeUpdateBody) => activityTypesApi.update(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: activityTypeKeys.all }),
  });
}

export function useDeactivateActivityType() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => activityTypesApi.deactivate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: activityTypeKeys.all }),
  });
}
