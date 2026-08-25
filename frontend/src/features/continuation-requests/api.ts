import { api } from "@/lib/api-client";

import type {
  ContinuationRequest,
  ContinuationRequestCreateBody,
  ContinuationRequestListParams,
  ContinuationRequestPage,
  ContinuationReviewBody,
} from "./types";

function toQuery(p: ContinuationRequestListParams): string {
  const sp = new URLSearchParams();
  if (p.status) sp.set("status", p.status);
  sp.set("limit", String(p.limit));
  sp.set("offset", String(p.offset));
  return sp.toString();
}

export const continuationRequestsApi = {
  create: (body: ContinuationRequestCreateBody) =>
    api.post<ContinuationRequest>("/continuation-requests", body),
  pending: () => api.get<ContinuationRequest[]>("/continuation-requests/pending"),
  list: (params: ContinuationRequestListParams) =>
    api.get<ContinuationRequestPage>(`/continuation-requests?${toQuery(params)}`),
  get: (id: string) => api.get<ContinuationRequest>(`/continuation-requests/${id}`),
  approve: (id: string, body: ContinuationReviewBody) =>
    api.post<ContinuationRequest>(`/continuation-requests/${id}/approve`, body),
  reject: (id: string, body: ContinuationReviewBody) =>
    api.post<ContinuationRequest>(`/continuation-requests/${id}/reject`, body),
};
