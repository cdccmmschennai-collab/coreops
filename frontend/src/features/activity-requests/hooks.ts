import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { activityRequestsApi } from "./api";
import { activityRequestKeys } from "./keys";
import type { ActivityRequestCreateBody } from "./types";

/** PM: pending activity requests awaiting a decision. */
export function usePendingActivityRequests(enabled = true) {
  return useQuery({
    queryKey: activityRequestKeys.list("pending"),
    queryFn: () => activityRequestsApi.listPending(),
    enabled,
  });
}

/** PM: count of pending requests (drives the dashboard badge). */
export function useActivityRequestPendingCount(enabled = true) {
  return useQuery({
    queryKey: activityRequestKeys.pendingCount(),
    queryFn: () => activityRequestsApi.pendingCount(),
    enabled,
  });
}

/** Employee: create a request from the work-report form. */
export function useCreateActivityRequest() {
  return useMutation({
    mutationFn: (body: ActivityRequestCreateBody) =>
      activityRequestsApi.create(body),
  });
}

function useInvalidatePending() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: activityRequestKeys.list("pending") });
    qc.invalidateQueries({ queryKey: activityRequestKeys.pendingCount() });
  };
}

export function useApproveActivityRequest() {
  const invalidate = useInvalidatePending();
  return useMutation({
    mutationFn: (id: string) => activityRequestsApi.approve(id),
    onSuccess: invalidate,
  });
}

export function useRejectActivityRequest() {
  const invalidate = useInvalidatePending();
  return useMutation({
    mutationFn: (id: string) => activityRequestsApi.reject(id),
    onSuccess: invalidate,
  });
}
