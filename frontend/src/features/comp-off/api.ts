import { api } from "@/lib/api-client";

import type {
  CompOffApproveBody,
  CompOffListParams,
  CompOffRejectBody,
  CompOffRequest,
  CompOffRequestCreateBody,
  CompOffRequestPage,
} from "./types";

function toQuery(p: CompOffListParams): string {
  const sp = new URLSearchParams();
  if (p.status) sp.set("status", p.status);
  sp.set("limit", String(p.limit));
  sp.set("offset", String(p.offset));
  if (p.exclude_self) sp.set("exclude_self", "true");
  return sp.toString();
}

/** `backend/app/modules/comp_off/router.py`. No employee id is ever sent: the
 *  server scopes a non-manager to their own requests and takes the requester
 *  from the session, so the browser cannot ask for anyone else's. */
export const compOffApi = {
  list: (params: CompOffListParams) =>
    api.get<CompOffRequestPage>(`/comp-off-requests?${toQuery(params)}`),
  /** One request, with `employee_name` / `manager_name` resolved server-side.
   *  The server allows a PM or the request's author; anyone else gets 403. */
  get: (id: string) => api.get<CompOffRequest>(`/comp-off-requests/${id}`),
  create: (body: CompOffRequestCreateBody) =>
    api.post<CompOffRequest>("/comp-off-requests", body),
  approve: (id: string, body: CompOffApproveBody) =>
    api.post<CompOffRequest>(`/comp-off-requests/${id}/approve`, body),
  reject: (id: string, body: CompOffRejectBody) =>
    api.post<CompOffRequest>(`/comp-off-requests/${id}/reject`, body),
  cancel: (id: string) => api.post<CompOffRequest>(`/comp-off-requests/${id}/cancel`, {}),
};
