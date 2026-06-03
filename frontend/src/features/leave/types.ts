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

export interface LeaveListParams {
  employee_id?: string;
  status?: LeaveStatus | "";
  from?: string;
  to?: string;
  limit: number;
  offset: number;
}

export const LEAVE_TYPE_LABEL: Record<LeaveType, string> = {
  casual: "Casual",
  sick: "Sick",
  annual: "Annual",
  comp_off: "Comp Off",
  unpaid: "Unpaid",
  other: "Other",
};

export const LEAVE_TYPES: LeaveType[] = ["casual", "sick", "annual", "comp_off", "unpaid", "other"];
