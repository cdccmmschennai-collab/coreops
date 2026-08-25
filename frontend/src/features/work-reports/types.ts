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
// Task continuation (feature-flagged): an unfinished work item the current
// employee can continue in the report being written.
//
// `days_used` / `is_lumpsum` are served by GET /work-reports/open-tasks but are
// not in the checked-in openapi.json yet: regenerating it produces an
// unreviewable whole-file diff (BOM + escape + number-format churn from a
// different generator invocation - see the SDD ledger, D-9/D-17). They are
// declared here instead, matching backend OpenTaskOut exactly, and are optional
// so the code stays correct against a build served by an older backend.
export type OpenTask = components["schemas"]["OpenTaskOut"] & {
  /** Distinct report dates the item has been worked on, excluding this report. */
  days_used?: number;
  /** True only for a lump-sum activity - the kind measured in work days. */
  is_lumpsum?: boolean;
};
export type OpenTasks = Omit<components["schemas"]["OpenTasksOut"], "items"> & {
  items: OpenTask[];
};
// Report-filter scope for Heads / Activity Leads (GET /work-reports/scope):
// accessible projects, led activities per project, and active members.
// Informational only — the backend enforces the same scope on every endpoint.
export type ReportScope = components["schemas"]["ReportScopeOut"];
export type ReportScopeProject = components["schemas"]["ReportScopeProject"];

export interface WorkReportListParams {
  employee_id: string;
  project_id: string;
  status: WorkReportStatusFilter | "";
  from: string;
  to: string;
  limit: number;
  offset: number;
}
