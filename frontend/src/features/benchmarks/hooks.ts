import { useQuery } from "@tanstack/react-query";

import { benchmarksApi } from "./api";
import { benchmarksKeys } from "./keys";

export function useMyAlerts() {
  return useQuery({
    queryKey: benchmarksKeys.myAlerts(),
    queryFn: () => benchmarksApi.myAlerts(),
  });
}

// PM-only (GET /benchmarks/team-alerts requires project_manager). Only mount
// this from views already gated to managerial roles, or the request 403s.
export function useTeamAlerts() {
  return useQuery({
    queryKey: benchmarksKeys.teamAlerts(),
    queryFn: () => benchmarksApi.teamAlerts(),
  });
}
