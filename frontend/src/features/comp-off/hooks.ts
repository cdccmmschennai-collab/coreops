import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { attendanceKeys } from "@/features/attendance/keys";
import { biometricKeys } from "@/features/biometric/keys";

import { compOffApi } from "./api";
import { compOffKeys } from "./keys";
import type {
  CompOffApproveBody,
  CompOffListParams,
  CompOffRejectBody,
  CompOffRequestCreateBody,
} from "./types";

export function useCompOffList(params: CompOffListParams, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: compOffKeys.list(params),
    queryFn: () => compOffApi.list(params),
    placeholderData: (prev) => prev,
    enabled: options?.enabled ?? true,
  });
}

/** One request for the detail page. */
export function useCompOffRequest(id: string) {
  return useQuery({
    queryKey: compOffKeys.detail(id),
    queryFn: () => compOffApi.get(id),
    enabled: !!id,
  });
}

// Every mutation invalidates the comp off root, which covers the employee's own
// list, the review queue, the all-requests list and any open detail page. No mutation is
// retried: an approval writes attendance, so a blind retry is never safe.

export function useCreateCompOff() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CompOffRequestCreateBody) => compOffApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: compOffKeys.all }),
  });
}

export function useApproveCompOff() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: CompOffApproveBody }) =>
      compOffApi.approve(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: compOffKeys.all });
      // An approval writes the day off into attendance (Phase 4), so the
      // calendar and the daily review must re-read it.
      void qc.invalidateQueries({ queryKey: attendanceKeys.all });
      void qc.invalidateQueries({ queryKey: biometricKeys.all });
    },
  });
}

export function useRejectCompOff() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: CompOffRejectBody }) =>
      compOffApi.reject(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: compOffKeys.all }),
  });
}

export function useCancelCompOff() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => compOffApi.cancel(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: compOffKeys.all }),
  });
}
