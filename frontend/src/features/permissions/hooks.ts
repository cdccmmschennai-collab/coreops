import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { permissionApi } from "./api";
import { permissionKeys } from "./keys";
import type {
  PermissionListParams,
  PermissionRequestCreateBody,
  PermissionReviewBody,
} from "./types";

export function usePermissionList(params: PermissionListParams, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: permissionKeys.list(params),
    queryFn: () => permissionApi.list(params),
    placeholderData: (prev) => prev,
    enabled: options?.enabled ?? true,
  });
}

/** One request's full detail: names + balance context, one call. */
export function usePermissionRequest(id: string) {
  return useQuery({
    queryKey: permissionKeys.detail(id),
    queryFn: () => permissionApi.get(id),
    enabled: !!id,
  });
}

/** One calendar month of history AND that month's balance, in one call.
 *
 *  Both halves come from the same server-computed month bounds, so the table and
 *  the "2h / 4h" figure above it can never disagree - and no component recomputes
 *  the balance rule. */
export function usePermissionHistory(month: string, employeeId?: string) {
  return useQuery({
    queryKey: permissionKeys.history(month, employeeId),
    queryFn: () => permissionApi.history(month, employeeId),
    // Keeps the previous month on screen while the next one loads, so stepping
    // through months does not flash an empty table.
    placeholderData: (prev) => prev,
  });
}

/** The signed-in employee's own balance. No `month` = the current Chennai
 *  business month, resolved server-side. */
export function useMyPermissionBalance(month?: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: permissionKeys.myBalance(month),
    queryFn: () => permissionApi.myBalance(month),
    enabled: options?.enabled ?? true,
  });
}

/** Another employee's balance, for the review queue. Project-manager only. */
export function usePermissionBalance(
  employeeId: string | undefined,
  month?: string,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: permissionKeys.balance(employeeId ?? "", month),
    queryFn: () => permissionApi.balance(employeeId as string, month),
    enabled: (options?.enabled ?? true) && !!employeeId,
  });
}

// Every mutation invalidates the permission root, which covers the lists, the
// queue badge and - crucially - the KPI's balance in one go: an approval changes
// the remaining hours, so leaving the balance cached would show a stale figure.

export function useCreatePermission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PermissionRequestCreateBody) => permissionApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: permissionKeys.all }),
  });
}

export function useCancelPermission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => permissionApi.cancel(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: permissionKeys.all }),
  });
}

// The three cancellation mutations invalidate the same permission root, which
// covers the history table, the shared Cancellation requests queue, its badge
// count and the balance KPI in one go - only an APPROVED decision moves hours,
// but every one of them moves a row between queues.

export function useRequestPermissionCancellation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => permissionApi.requestCancellation(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: permissionKeys.all }),
  });
}

export function useApprovePermissionCancellation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => permissionApi.approveCancellation(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: permissionKeys.all }),
  });
}

export function useRejectPermissionCancellation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => permissionApi.rejectCancellation(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: permissionKeys.all }),
  });
}

export function useApprovePermission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: PermissionReviewBody }) =>
      permissionApi.approve(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: permissionKeys.all }),
  });
}

export function useRejectPermission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: PermissionReviewBody }) =>
      permissionApi.reject(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: permissionKeys.all }),
  });
}
