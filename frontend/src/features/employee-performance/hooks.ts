import { useQuery } from "@tanstack/react-query";

import { useAttendanceList } from "@/features/attendance/hooks";
import { todayISO, weekStartISO } from "@/features/dashboard/utils";
import { useWorkReportList } from "@/features/work-reports/hooks";

import { performanceApi } from "./api";
import { performanceKeys } from "./keys";
import type { PerformanceParams } from "./types";

// PM-only (both endpoints require project_manager). Only mount from views
// already gated to managerial roles, or the requests 403.
export function useEmployeesPerformance(params: PerformanceParams) {
  return useQuery({
    queryKey: performanceKeys.list(params),
    queryFn: () => performanceApi.list(params),
    placeholderData: (prev) => prev, // keep previous page while paginating/searching
  });
}

export function useEmployeeOverview(id: string | undefined) {
  return useQuery({
    queryKey: performanceKeys.overview(id ?? ""),
    queryFn: () => performanceApi.overview(id as string),
    enabled: !!id,
  });
}

/** Full weekly ledger for one employee (Benchmarks tab — reconciled client-side). */
export function useEmployeeBenchmarks(id: string | undefined) {
  return useQuery({
    queryKey: performanceKeys.benchmarks(id ?? ""),
    queryFn: () => performanceApi.benchmarks(id as string),
    enabled: !!id,
  });
}

// ── This-week views for the detail tabs ────────────────────────────────────────
// All employee-detail tabs are scoped to the current cycle (Fri → today),
// matching the benchmark module's Fri..Thu window. These reuse existing list
// endpoints filtered by employee + date range — no new APIs. todayISO/
// weekStartISO are deterministic within a day, so the query keys stay stable
// across renders.

/** This week's work reports for one employee (drives Projects / Tasks / Reports). */
export function useEmployeeWeekReports(employeeId: string) {
  return useWorkReportList({
    employee_id: employeeId,
    project_id: "",
    status: "",
    from: weekStartISO(),
    to: todayISO(),
    limit: 100, // /work-reports caps limit at 100; a week holds ≤7 reports anyway
    offset: 0,
  });
}

/** This week's attendance for one employee (drives the Attendance tab). */
export function useEmployeeWeekAttendance(employeeId: string) {
  return useAttendanceList({
    employee_id: employeeId,
    status: "",
    from: weekStartISO(),
    to: todayISO(),
    limit: 100,
    offset: 0,
  });
}
