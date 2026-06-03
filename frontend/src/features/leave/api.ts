import { api } from "@/lib/api-client";

import type {
  LeaveListParams,
  LeaveRequest,
  LeaveRequestCreateBody,
  LeaveRequestPage,
  LeaveRequestUpdateBody,
  LeaveReviewBody,
} from "./types";

function toQuery(p: LeaveListParams): string {
  const sp = new URLSearchParams();
  if (p.employee_id) sp.set("employee_id", p.employee_id);
  if (p.status) sp.set("status", p.status);
  if (p.from) sp.set("from", p.from);
  if (p.to) sp.set("to", p.to);
  sp.set("limit", String(p.limit));
  sp.set("offset", String(p.offset));
  return sp.toString();
}

export const leaveApi = {
  list: (params: LeaveListParams) =>
    api.get<LeaveRequestPage>(`/leave-requests?${toQuery(params)}`),
  get: (id: string) => api.get<LeaveRequest>(`/leave-requests/${id}`),
  create: (body: LeaveRequestCreateBody) => api.post<LeaveRequest>("/leave-requests", body),
  update: (id: string, body: LeaveRequestUpdateBody) =>
    api.patch<LeaveRequest>(`/leave-requests/${id}`, body),
  cancel: (id: string) => api.post<LeaveRequest>(`/leave-requests/${id}/cancel`, {}),
  approve: (id: string, body: LeaveReviewBody) =>
    api.post<LeaveRequest>(`/leave-requests/${id}/approve`, body),
  reject: (id: string, body: LeaveReviewBody) =>
    api.post<LeaveRequest>(`/leave-requests/${id}/reject`, body),
};
