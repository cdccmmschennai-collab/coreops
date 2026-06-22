"use client";

import { PageHeader } from "@/components/shell/page-header";
import { useAuth } from "@/features/auth/auth-provider";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { PerformanceTable } from "@/features/employee-performance/components/performance-table";

import { greeting } from "./utils";

/**
 * PM dashboard — a manager summary built around the Employee Performance
 * comparison table. All benchmark detail (weekly KPIs, backlog, overdue,
 * per-employee benchmarks/projects/tasks/reports/attendance) lives on the
 * employee detail route reached by clicking a table row.
 */
export function ProjectManagerDashboard() {
  const { user, employeeId } = useAuth();
  const { items: employeeOptions } = useEmployeeOptions();

  const employee = employeeId
    ? employeeOptions.find((e) => e.id === employeeId)
    : undefined;
  const displayName =
    employee?.full_name?.trim() || user?.email.split("@")[0] || "there";

  return (
    <>
      <PageHeader
        title={`${greeting()}, ${displayName}`}
        subtitle={`${new Date().toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })} · Team overview`}
      />

      {/* Employee Performance — the primary (and only) dashboard section.
          Row click → /dashboard/employees/{id} for all per-employee detail. */}
      <PerformanceTable />
    </>
  );
}
