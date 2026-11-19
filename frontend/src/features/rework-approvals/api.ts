import { api } from "@/lib/api-client";
import type { WorkReport } from "@/features/work-reports/types";

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
  /** Employee: replace the rejected row and resubmit it. Returns the report. */
  correct: (id: string, body: Record<string, unknown>) =>
    api.post<WorkReport>(`/rework-approvals/${id}/correct`, body),
  reject: (id: string, remarks: string) =>
    api.post<ReworkRequestDetail>(`/rework-approvals/${id}/reject`, { remarks: remarks.trim() }),
};
