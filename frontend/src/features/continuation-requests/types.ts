export type ContinuationRequestStatus = "pending" | "approved" | "rejected";

export interface ContinuationRequest {
  id: string;
  employee_id: string;
  work_item_id: string;
  project_id: string;
  sub_activity_id: string;
  original_report_date: string;
  allowed_duration_days: number;
  due_date: string;
  continuation_date: string;
  status: ContinuationRequestStatus;
  requested_at: string;
  reviewer_id: string | null;
  decision_comment: string | null;
  decided_at: string | null;
  employee_name: string;
  project_name: string;
  project_code: string;
  activity_name: string | null;
  sub_activity_name: string;
  reviewer_name: string | null;
  routed_to_name: string | null;
  routed_to_role: "head" | "manager" | null;
}

export interface ContinuationRequestPage {
  items: ContinuationRequest[];
  total: number;
  limit: number;
  offset: number;
}

export interface ContinuationRequestCreateBody {
  work_item_id: string;
  continuation_date: string;
}

export interface ContinuationReviewBody {
  comment?: string | null;
}

export interface ContinuationRequestListParams {
  status?: ContinuationRequestStatus | "";
  limit: number;
  offset: number;
}

export const CONTINUATION_STATUS_LABEL: Record<ContinuationRequestStatus, string> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
};
