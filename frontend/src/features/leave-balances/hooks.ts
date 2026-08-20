import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { leaveBalanceApi } from "./api";
import { leaveBalanceKeys } from "./keys";
import type {
  LeaveAllocationUpdateBody,
  LeaveBalanceListParams,
  LeaveBalanceUpdateBody,
} from "./types";

export function useLeaveBalances(params: LeaveBalanceListParams) {
  return useQuery({
    queryKey: leaveBalanceKeys.list(params),
    queryFn: () => leaveBalanceApi.list(params),
    placeholderData: (prev) => prev,
  });
}

/** The signed-in employee's own balance FOR ONE MONTH.
 *
 *  `month` is any date in the month (the attendance page always sends the 1st);
 *  omitting it asks the server for the current Chennai business month. It is part
 *  of the query key, so each month is cached separately and the card can never
 *  show one month's figure under another month's heading. */
export function useMyLeaveBalance(month?: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: leaveBalanceKeys.me(month),
    queryFn: () => leaveBalanceApi.me(month),
    enabled: options?.enabled ?? true,
  });
}

export function useLeaveBalanceHistory(
  employeeId: string | undefined,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: leaveBalanceKeys.history(employeeId ?? ""),
    queryFn: () => leaveBalanceApi.history(employeeId as string),
    enabled: (options?.enabled ?? true) && !!employeeId,
  });
}

// Both mutations invalidate the whole leave-balance root: a correction or a rate
// change moves the figure for the month it lands in AND every month after it
// (carry-forward), so invalidating one month's key would leave the rest stale.

export function useSetLeaveBalance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      employeeId,
      body,
    }: {
      employeeId: string;
      body: LeaveBalanceUpdateBody;
    }) => leaveBalanceApi.set(employeeId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: leaveBalanceKeys.all }),
  });
}

export function useSetLeaveAllocation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      employeeId,
      body,
    }: {
      employeeId: string;
      body: LeaveAllocationUpdateBody;
    }) => leaveBalanceApi.setAllocation(employeeId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: leaveBalanceKeys.all }),
  });
}
