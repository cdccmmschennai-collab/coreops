import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { workReportKeys } from "@/features/work-reports/keys";

import { reworkApprovalsApi } from "./api";
import { reworkApprovalKeys } from "./keys";
import type { ReworkFilters } from "./types";

export function useReworkRequests(filters: ReworkFilters) {
  return useQuery({
    queryKey: reworkApprovalKeys.list(filters),
    queryFn: () => reworkApprovalsApi.list(filters),
    placeholderData: keepPreviousData,
  });
}

/** PM home card / tab count. */
export function useReworkPendingCount(enabled = true) {
  return useQuery({
    queryKey: reworkApprovalKeys.pendingCount(),
    queryFn: () => reworkApprovalsApi.pendingCount(),
    enabled,
  });
}

export function useReworkFilterOptions() {
  return useQuery({
    queryKey: reworkApprovalKeys.filterOptions(),
    queryFn: () => reworkApprovalsApi.filterOptions(),
    staleTime: 60 * 1000,
  });
}

export function useReworkRequest(id: string) {
  return useQuery({
    queryKey: reworkApprovalKeys.detail(id),
    queryFn: () => reworkApprovalsApi.get(id),
    enabled: !!id,
  });
}

export function useDecideReworkRequest(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ kind, remarks }: { kind: "approve" | "reject"; remarks: string }) =>
      kind === "approve"
        ? reworkApprovalsApi.approve(id, remarks)
        : reworkApprovalsApi.reject(id, remarks),
    onSuccess: (data) => {
      qc.setQueryData(reworkApprovalKeys.detail(id), data);
      qc.invalidateQueries({ queryKey: reworkApprovalKeys.all });
      // The employee's report rows read their state off this request.
      qc.invalidateQueries({ queryKey: workReportKeys.all });
    },
  });
}
