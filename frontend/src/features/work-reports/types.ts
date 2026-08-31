import type { components } from "@/types/openapi";

// Types come straight from the live API contract (openapi-typescript output),
// except where a field the API already serves is not in the checked-in
// openapi.json yet - see WorkReportTask below.
export type WorkReportPeriod = Omit<
  components["schemas"]["WorkReportPeriodOut"],
  "tasks"
> & { tasks: WorkReportTask[] };
export type WorkReport = Omit<
  components["schemas"]["WorkReportOut"],
  "tasks" | "periods"
> & {
  tasks: WorkReportTask[];
  periods: WorkReportPeriod[];
  /** Continuations rejected on this report - detail read only, see below. */
  rejected_continuations?: RejectedContinuation[];
  /**
   * Who/what created the report (backend WorkReportOut.origin, migration 0079).
   * Declared here rather than off openapi.json for the same reason as the row
   * fields below, and optional so a build served by an older backend simply
   * reads as "not automatic" instead of crashing.
   *
   * Read-only: the client renders the AUTO badge from it and never writes it
   * back. It is never restamped server-side either, so an automatic report the
   * employee later edits stays "auto" - see isAutoReport in report-origin.ts.
   */
  origin?: ReportOrigin | null;
};
/** Report origin values the backend can serve (models.py ReportOrigin). */
export type ReportOrigin = "employee" | "auto";
/**
 * A lump-sum continuation the Project Head rejected on this report (backend
 * RejectedContinuationOut, migration 0077). The rows entered under it were
 * withdrawn from the activity list - they were never accepted work - so this
 * surviving request record is the only thing that keeps the employee's history
 * of "I asked to continue this, and it was refused" from disappearing.
 *
 * Declared here rather than off openapi.json for the same reason as the row
 * fields below, and optional so an older backend simply serves none.
 */
export interface RejectedContinuation {
  request_id: string;
  project_id: string;
  project_code?: string | null;
  activity_name?: string | null;
  sub_activity_name?: string | null;
  continuation_date: string;
  allowed_duration_days: number;
  reviewer_name?: string | null;
  decision_comment?: string | null;
  decided_at?: string | null;
}
export type WorkReportStatus = components["schemas"]["WorkReportStatus"];
// Adds the virtual "requested" value used ONLY by the list Status filter: a
// submitted report with a pending edit request. It is not a persisted status —
// the backend translates it to `submitted AND edit_requested_at IS NOT NULL`
// (see work_reports/schemas.py WorkReportStatusFilter).
export type WorkReportStatusFilter = WorkReportStatus | "requested";
export type WorkReportPage = Omit<
  components["schemas"]["WorkReportPage"],
  "items"
> & { items: WorkReport[] };
// `continuation_request_id` / `continuation_approval_status` are served by the
// API (backend WorkReportTaskOut, migration 0076) but are not in the checked-in
// openapi.json yet - regenerating it produces the same unreviewable whole-file
// diff described for OpenTask below. Declared here instead, optional so the code
// stays correct against a build served by an older backend, where every row
// simply reads "no approval was involved".
//
// The status is the linked request's CURRENT status, resolved server-side on
// every read:
//   null       - this row needed no approval;
//   "pending"  - entered and submitted, but not accepted work yet. The REPORT is
//                submitted normally; only marking the activity complete waits;
//   "approved" - ordinary recorded work.
// "rejected" does not reach the client on a row: rejecting withdraws these rows
// from the report, and what survives is the report's `rejected_continuations`
// record above. The value is still in the union because the editor derives a
// not-yet-saved row's state from the open task it continues, which can be a
// rejected one.
//
// `overall_is_lumpsum` / `overall_target_days` / `overall_days_used` are served
// alongside them (same backend schema, same reason for being declared here) and
// say how the row's overall task is MEASURED: a lump-sum activity spends its
// allowed duration in WORK DAYS, so its state is "Day N of M" / "Duration
// exceeded" rather than a calendar overdue count. `overall_days_used` counts the
// work days spent BEFORE this report's date - exactly OpenTask.days_used'
// convention - so this report is day used + 1. Null for a non-lump-sum row and
// for a completed one, neither of which is measured in work days. All optional,
// so an older backend simply falls back to the calendar presentation.
export type WorkReportTask = components["schemas"]["WorkReportTaskOut"] & {
  continuation_request_id?: string | null;
  continuation_approval_status?: "pending" | "approved" | "rejected" | null;
  overall_is_lumpsum?: boolean;
  overall_target_days?: number | null;
  overall_days_used?: number | null;
};
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
