"use client";

import { useQuery } from "@tanstack/react-query";

import { activityMasterApi } from "@/features/activity-master/api";
import { activityMasterKeys } from "@/features/activity-master/keys";
import { useAuth } from "@/features/auth/auth-provider";

/**
 * Benchmark Guide data source.
 *
 * Reuses the SAME authorized endpoint the Work Report activity selector uses
 * (GET /activity-master/sub-activities?active_only=true). The backend filters
 * RESTRICTED activities the caller may not use and excludes inactive rows, so
 * the guide never downloads-then-hides anything client-side.
 *
 * Live-update behaviour required by the guide:
 *   - fetch on open (the dialog only mounts this hook when it opens),
 *   - refetchOnWindowFocus so an Activity Master edit in another tab shows up,
 *   - a short staleTime so a reopen re-checks the server,
 *   - the query key lives under activityMasterKeys.all, so every Activity Master
 *     mutation (all of which invalidate `all`) refreshes the guide.
 *
 * The key carries a permission scope (role + employee id) so a session never
 * serves a different identity's access-filtered rows from cache.
 */
export function useBenchmarkGuide(enabled: boolean) {
  const { role, employeeId } = useAuth();
  const scope = `${role ?? "none"}:${employeeId ?? "none"}`;

  return useQuery({
    queryKey: activityMasterKeys.benchmarkGuide(scope),
    queryFn: () => activityMasterApi.listAllSubActivitiesFlat(true),
    enabled,
    staleTime: 45 * 1000,
    refetchOnWindowFocus: true,
  });
}
