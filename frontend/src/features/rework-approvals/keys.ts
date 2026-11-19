import type { ReworkFilters } from "./types";

export const reworkApprovalKeys = {
  all: ["rework-approvals"] as const,
  list: (filters: ReworkFilters) => [...reworkApprovalKeys.all, "list", filters] as const,
  pendingCount: () => [...reworkApprovalKeys.all, "pending-count"] as const,
  filterOptions: () => [...reworkApprovalKeys.all, "filter-options"] as const,
  detail: (id: string) => [...reworkApprovalKeys.all, "detail", id] as const,
};
