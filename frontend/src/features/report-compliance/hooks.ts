import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-provider";
import { isManagerial } from "@/lib/rbac";

import { reportComplianceApi } from "./api";

export const complianceKeys = {
  me: () => ["report-compliance", "me"] as const,
};

/**
 * The acting employee's report-compliance snapshot. Only enabled for
 * authenticated non-managerial users (the reminder / banner / logout guard are
 * employee-facing); managers never owe daily reports. Refetched every few
 * minutes so the 5:15 reminder and logout guard see fresh data without a reload.
 */
export function useMyCompliance() {
  const { status, role } = useAuth();
  const enabled = status === "authenticated" && !isManagerial(role);
  return useQuery({
    queryKey: complianceKeys.me(),
    queryFn: () => reportComplianceApi.me(),
    enabled,
    refetchInterval: 5 * 60_000,
    refetchOnWindowFocus: true,
    staleTime: 60_000,
  });
}
