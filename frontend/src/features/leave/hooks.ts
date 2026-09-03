import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { leaveApi } from "./api";
import { leaveKeys } from "./keys";
import type { AllRequestListParams } from "./all-requests";
import type {
  LeaveListParams,
  LeaveRequestCreateBody,
  LeaveRequestUpdateBody,
  LeaveReviewBody,
} from "./types";

/** The All Requests history - leave AND permission rows, one paged list.
 *
 *  `staleTime: 0` rather than the app's 30s default, because this one query is
 *  fed by TWO features' mutations: a leave decision invalidates `leaveKeys.all`
 *  and reaches it, but a permission decision invalidates the permission root and
 *  does not. The reader always arrives here by navigating - opening the tab, or
 *  coming back from a detail page after deciding - so refetching on mount closes
 *  that gap without polling, and `placeholderData` keeps the old rows on screen
 *  meanwhile so there is no skeleton flash. */
export function useAllRequests(
  params: AllRequestListParams,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: leaveKeys.allRequests(params),
    queryFn: () => leaveApi.allRequests(params),
    placeholderData: (prev) => prev,
    staleTime: 0,
    enabled: options?.enabled ?? true,
  });
}

export function useLeaveList(params: LeaveListParams, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: leaveKeys.list(params),
    queryFn: () => leaveApi.list(params),
    placeholderData: (prev) => prev,
    enabled: options?.enabled ?? true,
  });
}

export function useLeaveRequest(id: string) {
  return useQuery({
    queryKey: leaveKeys.detail(id),
    queryFn: () => leaveApi.get(id),
    enabled: !!id,
  });
}

/** Deliverable Impact for the currently displayed leave requests. Computed in
 *  one bulk call for all `ids`; disabled when there are no rows. */
export function useDeliverableImpact(ids: string[]) {
  return useQuery({
    queryKey: leaveKeys.deliverableImpact(ids),
    queryFn: () => leaveApi.deliverableImpact(ids),
    enabled: ids.length > 0,
    placeholderData: (prev) => prev,
  });
}

/** Live Normal/Special for the dates currently in the leave form.
 *
 *  Disabled until both dates are present and in order, so a half-filled form
 *  asks nothing. The answer is the backend's own working-day count, which is
 *  why the frozen "Leave type" the dialog shows cannot drift from the request
 *  that gets saved. */
export function useLeaveClassificationPreview(start: string, end: string) {
  return useQuery({
    queryKey: leaveKeys.classificationPreview(start, end),
    queryFn: () => leaveApi.classificationPreview(start, end),
    enabled: !!start && !!end && end >= start,
    placeholderData: (prev) => prev,
  });
}

export function useCreateLeave() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: LeaveRequestCreateBody) => leaveApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: leaveKeys.all }),
  });
}

export function useUpdateLeave(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: LeaveRequestUpdateBody) => leaveApi.update(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: leaveKeys.all }),
  });
}

/** Read-only attendance already recorded across the displayed cancellation
 *  requests. One bulk call for the whole table; PM-only endpoint. */
export function useLeaveAttendanceSummary(ids: string[]) {
  return useQuery({
    queryKey: leaveKeys.attendanceSummary(ids),
    queryFn: () => leaveApi.attendanceSummary(ids),
    enabled: ids.length > 0,
    placeholderData: (prev) => prev,
  });
}

export function useCancelLeave() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => leaveApi.cancel(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: leaveKeys.all }),
  });
}

// The three cancellation mutations all invalidate the leave-key root, which
// covers every list, detail, queue count and dashboard badge in one go.

export function useRequestLeaveCancellation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => leaveApi.requestCancellation(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: leaveKeys.all }),
  });
}

export function useApproveLeaveCancellation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => leaveApi.approveCancellation(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: leaveKeys.all }),
  });
}

export function useRejectLeaveCancellation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => leaveApi.rejectCancellation(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: leaveKeys.all }),
  });
}

export function useApproveLeave() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: LeaveReviewBody }) =>
      leaveApi.approve(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: leaveKeys.all }),
  });
}

export function useRejectLeave() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: LeaveReviewBody }) =>
      leaveApi.reject(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: leaveKeys.all }),
  });
}
