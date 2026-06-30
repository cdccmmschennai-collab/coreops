import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { leaveApi } from "./api";
import { leaveKeys } from "./keys";
import type {
  LeaveListParams,
  LeaveRequestCreateBody,
  LeaveRequestUpdateBody,
  LeaveReviewBody,
} from "./types";

export function useLeaveList(params: LeaveListParams) {
  return useQuery({
    queryKey: leaveKeys.list(params),
    queryFn: () => leaveApi.list(params),
    placeholderData: (prev) => prev,
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

export function useCancelLeave() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => leaveApi.cancel(id),
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
