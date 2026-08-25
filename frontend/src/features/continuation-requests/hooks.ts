import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { workReportKeys } from "@/features/work-reports/keys";

import { continuationRequestsApi } from "./api";
import { continuationRequestKeys } from "./keys";
import type {
  ContinuationRequestCreateBody,
  ContinuationRequestListParams,
  ContinuationReviewBody,
} from "./types";

export function usePendingContinuationRequests(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: continuationRequestKeys.pending(),
    queryFn: () => continuationRequestsApi.pending(),
    enabled: options?.enabled ?? true,
  });
}

export function useContinuationRequestList(
  params: ContinuationRequestListParams,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: continuationRequestKeys.list(params),
    queryFn: () => continuationRequestsApi.list(params),
    placeholderData: (prev) => prev,
    enabled: options?.enabled ?? true,
  });
}

export function useContinuationRequest(id: string) {
  return useQuery({
    queryKey: continuationRequestKeys.detail(id),
    queryFn: () => continuationRequestsApi.get(id),
    enabled: !!id,
  });
}

export function useCreateContinuationRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ContinuationRequestCreateBody) => continuationRequestsApi.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: continuationRequestKeys.all });
      // The employee's "Open tasks" card must flip to the new pending state.
      qc.invalidateQueries({ queryKey: workReportKeys.all });
    },
  });
}

export function useApproveContinuationRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ContinuationReviewBody }) =>
      continuationRequestsApi.approve(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: continuationRequestKeys.all }),
  });
}

export function useRejectContinuationRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ContinuationReviewBody }) =>
      continuationRequestsApi.reject(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: continuationRequestKeys.all }),
  });
}
