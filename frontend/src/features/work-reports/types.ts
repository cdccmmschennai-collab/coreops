import type { components } from "@/types/openapi";

// Types come straight from the live API contract (openapi-typescript output).
export type WorkReport = components["schemas"]["WorkReportOut"];
export type WorkReportStatus = components["schemas"]["WorkReportStatus"];
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
  status: WorkReportStatus | "";
  from: string;
  to: string;
  limit: number;
  offset: number;
}
