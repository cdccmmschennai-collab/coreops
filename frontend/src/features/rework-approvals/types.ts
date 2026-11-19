export type ReworkStatus = "pending" | "approved" | "rejected" | "cancelled";

export interface ReworkRequest {
  id: string;
  report_id: string | null;
  employee_id: string;
  employee_code: string;
  employee_name: string;
  project_id: string;
  project_code: string | null;
  project_name: string | null;
  activity_id: string | null;
  activity_name: string | null;
  sub_activity_id: string;
  sub_activity_name: string;
  report_date: string;
  day_part: string;
  employee_remarks: string | null;
  status: ReworkStatus;
  cycle_no: number;
  requested_at: string;
  requested_by_name: string | null;
  reviewer_name: string | null;
  review_remarks: string | null;
  decided_at: string | null;
  can_review: boolean;
}

export interface ReportActivity {
  activity_name: string | null;
  sub_activity_name: string | null;
  project_code: string | null;
  day_part: string | null;
  description: string | null;
  rework_approval_status: ReworkStatus | null;
}

export interface ReworkRequestDetail extends ReworkRequest {
  history: ReworkRequest[];
  report_status: string | null;
  report_activities: ReportActivity[];
}

export interface ReworkCounts {
  pending: number;
  approved: number;
  rejected: number;
}

export interface ReworkRequestPage {
  items: ReworkRequest[];
  total: number;
  limit: number;
  offset: number;
  counts: ReworkCounts;
}

export interface FilterOption {
  value: string;
  label: string;
}

export interface ReworkFilterOptions {
  projects: FilterOption[];
  employees: FilterOption[];
  activities: FilterOption[];
}

/** Empty string = no filter, which is also how useUrlState stores "unset". */
export interface ReworkFilters {
  status: string;
  project_id: string;
  employee_id: string;
  report_date: string;
  sub_activity_id: string;
  offset: number;
}
