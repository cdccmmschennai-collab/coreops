import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { submissionsApi } from "./api";
import { submissionsKeys } from "./keys";
import type {
  SubmissionCreateBody,
  SubmissionStatusUpdateBody,
  SubmissionUpdateBody,
} from "./types";

export function useSubmissions(projectId: string) {
  return useQuery({
    queryKey: submissionsKeys.all(projectId),
    queryFn: () => submissionsApi.list(projectId),
    enabled: !!projectId,
  });
}

export function useSubmission(projectId: string, id: string | undefined) {
  return useQuery({
    queryKey: submissionsKeys.detail(projectId, id ?? ""),
    queryFn: () => submissionsApi.get(projectId, id as string),
    enabled: !!id,
  });
}

function useInvalidate(projectId: string, id?: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: submissionsKeys.all(projectId) });
    if (id) qc.invalidateQueries({ queryKey: submissionsKeys.detail(projectId, id) });
  };
}

export function useCreateSubmission(projectId: string) {
  const invalidate = useInvalidate(projectId);
  return useMutation({
    mutationFn: (body: SubmissionCreateBody) => submissionsApi.create(projectId, body),
    onSuccess: invalidate,
  });
}

export function useUpdateSubmission(projectId: string, id: string) {
  const invalidate = useInvalidate(projectId, id);
  return useMutation({
    mutationFn: (body: SubmissionUpdateBody) => submissionsApi.update(projectId, id, body),
    onSuccess: invalidate,
  });
}

export function useUpdateSubmissionStatus(projectId: string, id: string) {
  const invalidate = useInvalidate(projectId, id);
  return useMutation({
    mutationFn: (body: SubmissionStatusUpdateBody) =>
      submissionsApi.updateStatus(projectId, id, body),
    onSuccess: invalidate,
  });
}

export function useDeleteSubmission(projectId: string) {
  const invalidate = useInvalidate(projectId);
  return useMutation({
    mutationFn: (id: string) => submissionsApi.delete(projectId, id),
    onSuccess: invalidate,
  });
}
