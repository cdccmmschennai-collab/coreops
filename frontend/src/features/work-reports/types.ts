import type { components } from "@/types/openapi";

// Types come straight from the live API contract (openapi-typescript output).
export type WorkReport = components["schemas"]["WorkReportOut"];
export type WorkReportStatus = components["schemas"]["WorkReportStatus"];
// Adds the virtual "requested" value used ONLY by the list Status filter: a
// submitted report with a pending edit request. It is not a persisted status —
// the backend translates it to `submitted AND edit_requested_at IS NOT NULL`
// (see work_reports/schemas.py WorkReportStatusFilter).
export type WorkReportStatusFilter = WorkReportStatus | "requested";
export type WorkReportPage = components["schemas"]["WorkReportPage"];
export type WorkReportTask = components["schemas"]["WorkReportTaskOut"];
export type WorkReportTaskInput = components["schemas"]["WorkReportTaskIn"];
export type WorkReportCreateBody = components["schemas"]["WorkReportCreate"];
export type WorkReportUpdateBody = components["schemas"]["WorkReportUpdate"];
export type WorkReportEditRequestBody = components["schemas"]["WorkReportEditRequest"];
export type TaskCompletionUpdateBody = components["schemas"]["TaskCompletionUpdate"];

export interface WorkReportListParams {
  employee_id: string;
  project_id: string;
  status: WorkReportStatusFilter | "";
  from: string;
  to: string;
  limit: number;
  offset: number;
}
