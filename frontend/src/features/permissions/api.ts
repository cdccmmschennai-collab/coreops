import { api } from "@/lib/api-client";

import type {
  PermissionBalance,
  PermissionHistory,
  PermissionListParams,
  PermissionRequest,
  PermissionRequestCreateBody,
  PermissionRequestDetail,
  PermissionRequestPage,
  PermissionReviewBody,
} from "./types";

function toQuery(p: PermissionListParams): string {
  const sp = new URLSearchParams();
  if (p.employee_id) sp.set("employee_id", p.employee_id);
  if (p.status) sp.set("status", p.status);
  if (p.from) sp.set("from", p.from);
  if (p.to) sp.set("to", p.to);
  sp.set("limit", String(p.limit));
  sp.set("offset", String(p.offset));
  if (p.exclude_self) sp.set("exclude_self", "true");
  return sp.toString();
}

function monthQuery(month?: string): string {
  return month ? `?month=${month}` : "";
}

export const permissionApi = {
  list: (params: PermissionListParams) =>
    api.get<PermissionRequestPage>(`/permission-requests?${toQuery(params)}`),
  // The detail response carries the names and the balance context, so the detail
  // page needs exactly one call and does no arithmetic.
  get: (id: string) => api.get<PermissionRequestDetail>(`/permission-requests/${id}`),
  /** One calendar month of history plus that month's balance. `month` is any date
   *  in the month (we always send the 1st); omitting it asks for the current
   *  business month. */
  history: (month?: string, employeeId?: string) => {
    const sp = new URLSearchParams();
    if (month) sp.set("month", month);
    if (employeeId) sp.set("employee_id", employeeId);
    const qs = sp.toString();
    return api.get<PermissionHistory>(`/permission-requests/history${qs ? `?${qs}` : ""}`);
  },
  create: (body: PermissionRequestCreateBody) =>
    api.post<PermissionRequest>("/permission-requests", body),
  cancel: (id: string) =>
    api.post<PermissionRequest>(`/permission-requests/${id}/cancel`, {}),
  approve: (id: string, body: PermissionReviewBody) =>
    api.post<PermissionRequest>(`/permission-requests/${id}/approve`, body),
  reject: (id: string, body: PermissionReviewBody) =>
    api.post<PermissionRequest>(`/permission-requests/${id}/reject`, body),
  // Omitting `month` asks the server for the CURRENT Chennai business month,
  // which is what the KPI wants - the client never computes the month itself.
  myBalance: (month?: string) =>
    api.get<PermissionBalance>(`/permission-requests/balance/me${monthQuery(month)}`),
  balance: (employeeId: string, month?: string) =>
    api.get<PermissionBalance>(
      `/permission-requests/balance/${employeeId}${monthQuery(month)}`,
    ),
};
