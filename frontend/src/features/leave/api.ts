import { api } from "@/lib/api-client";

import type { AllRequestListParams, AllRequestPage } from "./all-requests";
import type {
  AttendanceSummaryResponse,
  DeliverableImpactResponse,
  LeaveClassificationPreview,
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
  if (p.exclude_self) sp.set("exclude_self", "true");
  sp.set("limit", String(p.limit));
  sp.set("offset", String(p.offset));
  return sp.toString();
}

export const leaveApi = {
  list: (params: LeaveListParams) =>
    api.get<LeaveRequestPage>(`/leave-requests?${toQuery(params)}`),
  /** The All Requests history - leave AND permission, already scoped, filtered,
   *  sorted and paged server-side. Takes the SAME query shape `list` does, so
   *  the tab's existing URL filters pass straight through unchanged. */
  allRequests: (params: AllRequestListParams) =>
    api.get<AllRequestPage>(`/all-requests?${toQuery(params)}`),
  get: (id: string) => api.get<LeaveRequest>(`/leave-requests/${id}`),
  create: (body: LeaveRequestCreateBody) => api.post<LeaveRequest>("/leave-requests", body),
  update: (id: string, body: LeaveRequestUpdateBody) =>
    api.patch<LeaveRequest>(`/leave-requests/${id}`, body),
  cancel: (id: string) => api.post<LeaveRequest>(`/leave-requests/${id}/cancel`, {}),
  requestCancellation: (id: string) =>
    api.post<LeaveRequest>(`/leave-requests/${id}/request-cancellation`, {}),
  approveCancellation: (id: string) =>
    api.post<LeaveRequest>(`/leave-requests/${id}/approve-cancellation`, {}),
  rejectCancellation: (id: string) =>
    api.post<LeaveRequest>(`/leave-requests/${id}/reject-cancellation`, {}),
  approve: (id: string, body: LeaveReviewBody) =>
    api.post<LeaveRequest>(`/leave-requests/${id}/approve`, body),
  reject: (id: string, body: LeaveReviewBody) =>
    api.post<LeaveRequest>(`/leave-requests/${id}/reject`, body),
  deliverableImpact: (ids: string[]) =>
    api.post<DeliverableImpactResponse>("/leave-requests/deliverable-impact", {
      leave_request_ids: ids,
    }),
  /** What a range would cost and be classified as, before it is filed. The
   *  form never works this out itself - the office week and the company
   *  calendar are the server's. */
  classificationPreview: (start: string, end: string) =>
    api.get<LeaveClassificationPreview>(
      `/leave-requests/classification-preview?start_date=${start}&end_date=${end}`,
    ),
  attendanceSummary: (ids: string[]) =>
    api.post<AttendanceSummaryResponse>("/leave-requests/attendance-summary", {
      leave_request_ids: ids,
    }),
};
