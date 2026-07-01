export type ActivityRequestStatus = "pending" | "approved" | "rejected";

export interface ActivityRequest {
  id: string;
  employee_id: string;
  project_id: string;
  activity_id: string | null;
  sub_activity_id: string;
  task_id: string | null;
  tags_count: number;
  docs_count: number;
  bom_count: number;
  spares_count: number;
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
}

export interface ActivityRequestCreateBody {
  project_id: string;
  activity_id?: string | null;
  sub_activity_id: string;
  task_id?: string | null;
  tags_count?: number;
  docs_count?: number;
  bom_count?: number;
  spares_count?: number;
}

export const ACTIVITY_REQUEST_STATUS_LABEL: Record<ActivityRequestStatus, string> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
};
