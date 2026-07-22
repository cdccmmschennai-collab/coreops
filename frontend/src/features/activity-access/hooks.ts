import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { activityMasterKeys } from "@/features/activity-master/keys";

import { activityAccessApi } from "./api";
import { activityAccessKeys } from "./keys";
import { canSearchEmployees, type AccessType } from "./types";

/** Paginated access config for one activity. `enabled` gates the fetch so the
 *  Access tab only loads when the PM opens it (lazy-load, Phase 12). */
export function useActivityAccess(
  activityId: string,
  limit: number,
  offset: number,
  enabled: boolean,
) {
  return useQuery({
    queryKey: activityAccessKeys.config(activityId, limit, offset),
    queryFn: () => activityAccessApi.getConfig(activityId, limit, offset),
    enabled,
    // Access changes are infrequent; keep it fresh-ish but not chatty.
    staleTime: 30 * 1000,
  });
}

/** Debounced server-side employee search for the grant picker. The caller
 *  passes an already-debounced query; we gate on >= 2 chars and let React Query
 *  cancel stale requests via the AbortSignal it provides. */
export function useEmployeeAccessSearch(activityId: string, q: string) {
  return useQuery({
    queryKey: activityAccessKeys.search(activityId, q),
    queryFn: ({ signal }) => activityAccessApi.searchEmployees(activityId, q, signal),
    enabled: canSearchEmployees(q),
    staleTime: 10 * 1000,
  });
}

function useInvalidateAccess() {
  const qc = useQueryClient();
  return (activityId: string) => {
    // Refresh the access config + the activity list (badge/count) after a
    // mutation. Clearing stale access-query data is important on make-common.
    qc.invalidateQueries({ queryKey: activityAccessKeys.all });
    qc.invalidateQueries({ queryKey: activityMasterKeys.all });
    void activityId;
  };
}

export function useChangeAccessType(activityId: string) {
  const invalidate = useInvalidateAccess();
  return useMutation({
    mutationFn: (body: { access_type: AccessType; employee_ids?: string[] }) =>
      activityAccessApi.changeAccessType(activityId, body),
    onSuccess: () => invalidate(activityId),
  });
}

export function useGrantAccess(activityId: string) {
  const invalidate = useInvalidateAccess();
  return useMutation({
    mutationFn: (employeeIds: string[]) =>
      activityAccessApi.grant(activityId, employeeIds),
    onSuccess: () => invalidate(activityId),
  });
}

export function useRevokeAccess(activityId: string) {
  const invalidate = useInvalidateAccess();
  return useMutation({
    mutationFn: (employeeId: string) => activityAccessApi.revoke(activityId, employeeId),
    onSuccess: () => invalidate(activityId),
  });
}
