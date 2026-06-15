import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { projectActivitiesApi } from "./api";
import { activityKeys } from "./keys";
import type { ProjectActivityCreateBody, ProjectActivityUpdateBody } from "./types";

export function useProjectActivities(projectId: string) {
  return useQuery({
    queryKey: activityKeys.all(projectId),
    queryFn: () => projectActivitiesApi.list(projectId),
    enabled: !!projectId,
  });
}

function useInvalidate(projectId: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: activityKeys.all(projectId) });
}

export function useCreateActivity(projectId: string) {
  const invalidate = useInvalidate(projectId);
  return useMutation({
    mutationFn: (body: ProjectActivityCreateBody) =>
      projectActivitiesApi.create(projectId, body),
    onSuccess: invalidate,
  });
}

export function useUpdateActivity(projectId: string, id: string) {
  const invalidate = useInvalidate(projectId);
  return useMutation({
    mutationFn: (body: ProjectActivityUpdateBody) =>
      projectActivitiesApi.update(projectId, id, body),
    onSuccess: invalidate,
  });
}

export function useDeleteActivity(projectId: string) {
  const invalidate = useInvalidate(projectId);
  return useMutation({
    mutationFn: (id: string) => projectActivitiesApi.delete(projectId, id),
    onSuccess: invalidate,
  });
}
