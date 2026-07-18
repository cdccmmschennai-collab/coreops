export type ActivityRequestStatus = "pending" | "approved" | "rejected";

export interface ActivityRequest {
  id: string;
  employee_id: string;
  report_id: string | null;
  project_id: string;
  activity_id: string | null;
  sub_activity_id: string;
  task_id: string | null;
  // Requested workload hints — never benchmark inputs. Copied onto the
  // work-report row when the PM approves; the request itself never produces
  // performance, completion or pending.
  tags_count: number;
  docs_count: number;
  bom_count: number;
  spares_count: number;
  pages_count: number;
  records_count: number;
  status: ActivityRequestStatus;
  requested_at: string;
  approved_by: string | null;
  approved_at: string | null;
  // Display-only names resolved by the backend.
  employee_name: string;
  project_name: string;
  project_code: string;
  activity_name: string | null;
  sub_activity_name: string;
  task_title: string | null;
  // The employee's current (first) activity already logged in the report, so
  // the PM can compare it against the requested activity.
  current_project_name: string | null;
  current_project_code: string | null;
  current_activity_name: string | null;
  current_sub_activity_name: string | null;
}

export interface ActivityRequestCreateBody {
  report_id: string;
  project_id: string;
  activity_id?: string | null;
  sub_activity_id: string;
  task_id?: string | null;
  tags_count?: number;
  docs_count?: number;
  bom_count?: number;
  spares_count?: number;
  pages_count?: number;
  records_count?: number;
}

export const ACTIVITY_REQUEST_STATUS_LABEL: Record<ActivityRequestStatus, string> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
};
