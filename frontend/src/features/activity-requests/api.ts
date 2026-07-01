import { api } from "@/lib/api-client";

import type { ActivityRequest, ActivityRequestCreateBody } from "./types";

export const activityRequestsApi = {
  listPending: () =>
    api.get<ActivityRequest[]>(`/activity-requests?status=pending`),

  pendingCount: () =>
    api.get<{ count: number }>(`/activity-requests/pending-count`),

  create: (body: ActivityRequestCreateBody) =>
    api.post<ActivityRequest>(`/activity-requests`, body),

  approve: (id: string) =>
    api.post<ActivityRequest>(`/activity-requests/${id}/approve`),

  reject: (id: string) =>
    api.post<ActivityRequest>(`/activity-requests/${id}/reject`),
};
