import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { leaveBalanceApi } from "./api";
import { leaveBalanceKeys } from "./keys";
import type { LeaveBalanceListParams, LeaveBalanceUpdateBody } from "./types";

export function useLeaveBalances(params: LeaveBalanceListParams) {
  return useQuery({
    queryKey: leaveBalanceKeys.list(params),
    queryFn: () => leaveBalanceApi.list(params),
    placeholderData: (prev) => prev,
  });
}

export function useMyLeaveBalance(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: leaveBalanceKeys.me(),
    queryFn: () => leaveBalanceApi.me(),
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
