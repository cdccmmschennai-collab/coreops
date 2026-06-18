import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  activityMasterApi,
  type ActivityCreateBody,
  type ActivityMasterUpdateBody,
  type SubActivityCreateBody,
} from "./api";
import { activityMasterKeys } from "./keys";

export function useActivities(activeOnly?: boolean) {
  return useQuery({
    queryKey: activityMasterKeys.activities(activeOnly),
    queryFn: () => activityMasterApi.listActivities(activeOnly),
    staleTime: 5 * 60 * 1000,
  });
}

export function useSubActivities(activityId: string | null, activeOnly?: boolean) {
  return useQuery({
    queryKey: activityMasterKeys.subActivities(activityId ?? "", activeOnly),
    queryFn: () => activityMasterApi.listSubActivities(activityId as string, activeOnly),
    enabled: !!activityId,
    staleTime: 5 * 60 * 1000,
  });
}

/** Flat list of every active sub-activity (with its parent Activity's name) —
 * the source for the Daily Work Report's cascading Activity / Sub-Activity
 * selects. */
export function useSubActivityOptions() {
  const query = useQuery({
    queryKey: activityMasterKeys.flatSubActivities(true),
    queryFn: () => activityMasterApi.listAllSubActivitiesFlat(true),
    staleTime: 5 * 60 * 1000,
  });
  const items = query.data ?? [];
  const byId = new Map(items.map((s) => [s.id, s]));
  return { items, byId, isLoading: query.isLoading };
}

function useInvalidateActivityMaster() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: activityMasterKeys.all });
}

export function useCreateActivity() {
  const invalidate = useInvalidateActivityMaster();
  return useMutation({
    mutationFn: (body: ActivityCreateBody) => activityMasterApi.createActivity(body),
    onSuccess: invalidate,
  });
}

export function useUpdateActivity(id: string) {
  const invalidate = useInvalidateActivityMaster();
  return useMutation({
    mutationFn: (body: ActivityMasterUpdateBody) => activityMasterApi.updateActivity(id, body),
    onSuccess: invalidate,
  });
}

export function useDeactivateActivity() {
  const invalidate = useInvalidateActivityMaster();
  return useMutation({
    mutationFn: (id: string) => activityMasterApi.deactivateActivity(id),
    onSuccess: invalidate,
  });
}

export function useCreateSubActivity(activityId: string) {
  const invalidate = useInvalidateActivityMaster();
  return useMutation({
    mutationFn: (body: SubActivityCreateBody) => activityMasterApi.createSubActivity(activityId, body),
    onSuccess: invalidate,
  });
}

export function useUpdateSubActivity(id: string) {
  const invalidate = useInvalidateActivityMaster();
  return useMutation({
    mutationFn: (body: ActivityMasterUpdateBody) => activityMasterApi.updateSubActivity(id, body),
    onSuccess: invalidate,
  });
}

export function useDeactivateSubActivity() {
  const invalidate = useInvalidateActivityMaster();
  return useMutation({
    mutationFn: (id: string) => activityMasterApi.deactivateSubActivity(id),
    onSuccess: invalidate,
  });
}
