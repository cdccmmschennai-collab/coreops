import { api } from "@/lib/api-client";

import type {
  LeaveAllocation,
  LeaveAllocationUpdateBody,
  LeaveBalance,
  LeaveBalanceHistoryPage,
  LeaveBalanceListParams,
  LeaveBalancePage,
  LeaveBalanceUpdateBody,
  MyLeaveBalance,
} from "./types";

function toQuery(p: LeaveBalanceListParams): string {
  const sp = new URLSearchParams();
  if (p.q) sp.set("q", p.q);
  if (p.sort_dir) sp.set("sort_dir", p.sort_dir);
  // The month the table describes. Omitting it asks the server for the current
  // Chennai business month - the client never resolves "now" itself.
  if (p.month) sp.set("month", p.month);
  sp.set("limit", String(p.limit));
  sp.set("offset", String(p.offset));
  return sp.toString();
}

function monthQuery(month?: string): string {
  return month ? `?month=${month}` : "";
}

export const leaveBalanceApi = {
  list: (params: LeaveBalanceListParams) =>
    api.get<LeaveBalancePage>(`/leave-balances?${toQuery(params)}`),
  me: (month?: string) =>
    api.get<MyLeaveBalance>(`/leave-balances/me${monthQuery(month)}`),
  set: (employeeId: string, body: LeaveBalanceUpdateBody) =>
    api.post<LeaveBalance>(`/leave-balances/${employeeId}`, body),
  /** `Leave/month`, from `body.effective_from` onwards. PUT because it is
   *  idempotent per effective month: saving the same month twice settles on one
   *  row rather than stacking two rates. */
  setAllocation: (employeeId: string, body: LeaveAllocationUpdateBody) =>
    api.put<LeaveAllocation>(`/leave-balances/${employeeId}/allocation`, body),
  history: (employeeId: string, limit = 50, offset = 0) =>
    api.get<LeaveBalanceHistoryPage>(
      `/leave-balances/${employeeId}/history?limit=${limit}&offset=${offset}`,
    ),
};
