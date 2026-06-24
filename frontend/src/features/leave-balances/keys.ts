import type { LeaveBalanceListParams } from "./types";

export const leaveBalanceKeys = {
  all: ["leave-balances"] as const,
  list: (params: LeaveBalanceListParams) =>
    [...leaveBalanceKeys.all, "list", params] as const,
  me: () => [...leaveBalanceKeys.all, "me"] as const,
  history: (employeeId: string) =>
    [...leaveBalanceKeys.all, "history", employeeId] as const,
};
