import type { LeaveBalanceListParams } from "./types";

/** Query keys. The MONTH is part of every balance key, which is what makes
 *  stepping August -> September -> October safe: each month is a separate cache
 *  entry, so a slow response for one month can never land in another month's
 *  card, and returning to August reads August's own entry back. */
export const leaveBalanceKeys = {
  all: ["leave-balances"] as const,
  // `params` already carries `month`.
  list: (params: LeaveBalanceListParams) =>
    [...leaveBalanceKeys.all, "list", params] as const,
  me: (month?: string) => [...leaveBalanceKeys.all, "me", month ?? ""] as const,
  history: (employeeId: string) =>
    [...leaveBalanceKeys.all, "history", employeeId] as const,
};
