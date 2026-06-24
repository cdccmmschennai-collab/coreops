export interface LeaveBalance {
  employee_id: string;
  employee_code: string;
  employee_name: string;
  available_leave: number;
  last_updated: string | null;
}

export interface LeaveBalancePage {
  items: LeaveBalance[];
  total: number;
  limit: number;
  offset: number;
}

export interface MyLeaveBalance {
  employee_id: string;
  available_leave: number;
  last_updated: string | null;
}

export interface LeaveBalanceUpdateBody {
  available_leave: number;
  reason: string;
}

export interface LeaveBalanceHistory {
  id: string;
  employee_id: string;
  old_balance: number | null;
  new_balance: number;
  reason: string;
  updated_by: string | null;
  updated_by_name: string | null;
  created_at: string;
}

export interface LeaveBalanceHistoryPage {
  items: LeaveBalanceHistory[];
  total: number;
  limit: number;
  offset: number;
}

export type SortDir = "asc" | "desc";

export interface LeaveBalanceListParams {
  q?: string;
  sort_dir?: SortDir;
  limit: number;
  offset: number;
}
