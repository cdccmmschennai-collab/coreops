import { useQuery } from "@tanstack/react-query";

import { reportsExportApi } from "./api";
import type { ActivityReportFilters } from "./types";

export function useActivityRows(filters: ActivityReportFilters) {
  return useQuery({
    queryKey: ["reports-export", "activity-rows", filters],
    queryFn: () => reportsExportApi.rows(filters),
    placeholderData: (prev) => prev,
  });
}

export function useActivityOptions() {
  return useQuery({
    queryKey: ["activity-master", "activities"],
    queryFn: () => reportsExportApi.activities(),
    staleTime: 5 * 60_000,
  });
}

export function useSubActivityOptions() {
  return useQuery({
    queryKey: ["activity-master", "sub-activities"],
    queryFn: () => reportsExportApi.subActivities(),
    staleTime: 5 * 60_000,
  });
}
