import { api } from "@/lib/api-client";

import { buildListQuery } from "./labels";
import type {
  ReworkFilterOptions,
  ReworkFilters,
  ReworkRequestDetail,
  ReworkRequestPage,
} from "./types";

export const reworkApprovalsApi = {
  list: (filters: ReworkFilters) =>
    api.get<ReworkRequestPage>(`/rework-approvals?${buildListQuery(filters)}`),
  pendingCount: () => api.get<{ count: number }>("/rework-approvals/pending-count"),
  filterOptions: () => api.get<ReworkFilterOptions>("/rework-approvals/filter-options"),
  get: (id: string) => api.get<ReworkRequestDetail>(`/rework-approvals/${id}`),
  approve: (id: string, remarks: string) =>
    api.post<ReworkRequestDetail>(`/rework-approvals/${id}/approve`, {
      remarks: remarks.trim() || null,
    }),
  reject: (id: string, remarks: string) =>
    api.post<ReworkRequestDetail>(`/rework-approvals/${id}/reject`, { remarks: remarks.trim() }),
};
