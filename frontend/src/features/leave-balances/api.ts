import { api } from "@/lib/api-client";

import type {
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
  sp.set("limit", String(p.limit));
  sp.set("offset", String(p.offset));
  return sp.toString();
}

export const leaveBalanceApi = {
  list: (params: LeaveBalanceListParams) =>
    api.get<LeaveBalancePage>(`/leave-balances?${toQuery(params)}`),
  me: () => api.get<MyLeaveBalance>("/leave-balances/me"),
  set: (employeeId: string, body: LeaveBalanceUpdateBody) =>
    api.post<LeaveBalance>(`/leave-balances/${employeeId}`, body),
  history: (employeeId: string, limit = 50, offset = 0) =>
    api.get<LeaveBalanceHistoryPage>(
      `/leave-balances/${employeeId}/history?limit=${limit}&offset=${offset}`,
    ),
};
