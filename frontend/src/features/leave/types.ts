export type LeaveType = "casual" | "sick" | "annual" | "comp_off" | "unpaid" | "other";
export type LeaveStatus = "pending" | "approved" | "rejected" | "cancelled";

export interface LeaveRequest {
  id: string;
  employee_id: string;
  leave_type: LeaveType;
  start_date: string;
  end_date: string;
  reason: string | null;
  status: LeaveStatus;
  manager_id: string | null;
  manager_comment: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeaveRequestPage {
  items: LeaveRequest[];
  total: number;
  limit: number;
  offset: number;
}

export interface LeaveRequestCreateBody {
  leave_type: LeaveType;
  start_date: string;
  end_date: string;
  reason?: string | null;
}

export interface LeaveRequestUpdateBody {
  leave_type?: LeaveType;
  start_date?: string;
  end_date?: string;
  reason?: string | null;
}

export interface LeaveReviewBody {
  comment?: string | null;
}

/** One Planned deliverable conflicting with a leave request (decision support). */
export interface DeliverableConflict {
  deliverable_id: string;
  deliverable_name: string;
  project_id: string;
  project_name: string | null;
  project_code: string | null;
  status: string;
  target_date: string | null;
  employee_id: string;
  employee_name: string | null;
}

export interface LeaveDeliverableImpact {
  leave_request_id: string;
  conflicts: DeliverableConflict[];
}

export interface DeliverableImpactResponse {
  items: LeaveDeliverableImpact[];
}

export interface LeaveListParams {
  employee_id?: string;
  status?: LeaveStatus | "";
  from?: string;
  to?: string;
  limit: number;
  offset: number;
}

// Full label map — keeps `sick`/`unpaid` so any historical requests still
// render correctly even though they're no longer offered when filing a new one.
export const LEAVE_TYPE_LABEL: Record<LeaveType, string> = {
  casual: "Casual",
  sick: "Sick",
  annual: "Annual",
  comp_off: "Comp Off",
  unpaid: "Unpaid",
  other: "Other",
};

// Selectable types when filing a leave request (Casual / Annual / Comp Off / Other).
// `sick` and `unpaid` are intentionally excluded — display-only legacy values.
export const SELECTABLE_LEAVE_TYPES = ["casual", "annual", "comp_off", "other"] as const;

export type SelectableLeaveType = (typeof SELECTABLE_LEAVE_TYPES)[number];

export const LEAVE_TYPES: LeaveType[] = [...SELECTABLE_LEAVE_TYPES];
