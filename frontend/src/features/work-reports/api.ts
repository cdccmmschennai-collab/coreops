import { api } from "@/lib/api-client";

import type {
  WorkReport,
  WorkReportCreateBody,
  WorkReportEditRequestBody,
  WorkReportListParams,
  WorkReportPage,
  WorkReportRejectBody,
  WorkReportUpdateBody,
} from "./types";

function toQuery(p: WorkReportListParams): string {
  const sp = new URLSearchParams();
  if (p.employee_id) sp.set("employee_id", p.employee_id);
  if (p.project_id) sp.set("project_id", p.project_id);
  if (p.status) sp.set("status", p.status);
  if (p.from) sp.set("from", p.from);
  if (p.to) sp.set("to", p.to);
  sp.set("limit", String(p.limit));
  sp.set("offset", String(p.offset));
  return sp.toString();
}

export const workReportsApi = {
  list: (params: WorkReportListParams) =>
    api.get<WorkReportPage>(`/work-reports?${toQuery(params)}`),
  get: (id: string) => api.get<WorkReport>(`/work-reports/${id}`),
  create: (body: WorkReportCreateBody) => api.post<WorkReport>("/work-reports", body),
  update: (id: string, body: WorkReportUpdateBody) =>
    api.patch<WorkReport>(`/work-reports/${id}`, body),
  submit: (id: string) => api.post<WorkReport>(`/work-reports/${id}/submit`),
  requestEdit: (id: string, body: WorkReportEditRequestBody) =>
    api.post<WorkReport>(`/work-reports/${id}/request-edit`, body),
  reject: (id: string, body: WorkReportRejectBody) =>
    api.post<WorkReport>(`/work-reports/${id}/reject`, body),
  grantEdit: (id: string) => api.post<WorkReport>(`/work-reports/${id}/grant-edit`),
  remove: (id: string) => api.del<void>(`/work-reports/${id}`),
};
