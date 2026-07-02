import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { workReportKeys } from "@/features/work-reports/keys";

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

/** Employee: their own pending/rejected requests for a given report. */
export function useMyActivityRequests(
  reportId: string | undefined,
  enabled = true,
) {
  return useQuery({
    queryKey: activityRequestKeys.mine(reportId ?? ""),
    queryFn: () => activityRequestsApi.listMine(reportId as string),
    enabled: enabled && !!reportId,
  });
}

/** Employee: create a request from the work-report form. */
export function useCreateActivityRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ActivityRequestCreateBody) =>
      activityRequestsApi.create(body),
    onSuccess: (_data, body) => {
      qc.invalidateQueries({ queryKey: activityRequestKeys.mine(body.report_id) });
    },
  });
}

/** Employee: dismiss/cancel their own (pending or rejected) request. */
export function useDeleteActivityRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => activityRequestsApi.remove(id),
    onSuccess: () => {
      // The report id isn't known here — refresh every "mine" list.
      qc.invalidateQueries({ queryKey: [...activityRequestKeys.all, "mine"] });
    },
  });
}

function useInvalidatePending() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: activityRequestKeys.list("pending") });
    qc.invalidateQueries({ queryKey: activityRequestKeys.pendingCount() });
    // A decision changes the employee's report (approved → new row) and their
    // own request lists — refresh both broadly.
    qc.invalidateQueries({ queryKey: workReportKeys.all });
    qc.invalidateQueries({ queryKey: [...activityRequestKeys.all, "mine"] });
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
