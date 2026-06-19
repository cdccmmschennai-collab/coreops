"use client";

import * as React from "react";

import { PageHeader } from "@/components/shell/page-header";
import { Kpi, KpiGrid } from "@/components/ui/kpi";
import { useAuth } from "@/features/auth/auth-provider";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { useTeamAlerts } from "@/features/benchmarks/hooks";
import { PerformanceTable } from "@/features/employee-performance/components/performance-table";

import { greeting } from "./utils";

/**
 * PM dashboard — deliberately two blocks only: a benchmark KPI summary and the
 * Employee Performance comparison table. All detailed analytics (backlog,
 * overdue, per-employee benchmarks/projects/tasks/reports/attendance) live on
 * the employee detail route reached by clicking a table row.
 */
export function ProjectManagerDashboard() {
  const { user, employeeId } = useAuth();
  const { items: employeeOptions } = useEmployeeOptions();

  const employee = employeeId
    ? employeeOptions.find((e) => e.id === employeeId)
    : undefined;
  const displayName =
    employee?.full_name?.trim() || user?.email.split("@")[0] || "there";

  const { data } = useTeamAlerts();
  const kpis = data?.kpis;

  const productivityLabel =
    kpis?.weekly_productivity_pct != null
      ? `${Number(kpis.weekly_productivity_pct).toFixed(0)}%`
      : "—";

  return (
    <>
      <PageHeader
        title={`${greeting()}, ${displayName}`}
        subtitle={`${new Date().toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })} · Team overview`}
      />

      {/* Weekly benchmark performance — four equal-weight KPI cards. */}
      <section className="mb-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">Weekly benchmark performance</h2>
          <span className="text-xs text-muted-foreground">This week · Mon–Fri</span>
        </div>

        <KpiGrid>
          <Kpi label="Team productivity" value={productivityLabel} />
          <Kpi label="Pending benchmarks" value={String(kpis?.total_pending_benchmarks ?? 0)} />
          <Kpi label="Overdue activities" value={String(kpis?.total_overdue_activities ?? 0)} />
          <Kpi label="Active employees" value={String(kpis?.total_employees ?? 0)} />
        </KpiGrid>
      </section>

      {/* Employee Performance — primary section. Row click → /dashboard/employees/{id} */}
      <PerformanceTable />
    </>
  );
}
