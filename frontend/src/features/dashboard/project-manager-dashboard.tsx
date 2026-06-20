"use client";

import * as React from "react";

import { PageHeader } from "@/components/shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Kpi, KpiGrid } from "@/components/ui/kpi";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAuth } from "@/features/auth/auth-provider";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { useTeamAlerts } from "@/features/benchmarks/hooks";
import { PerformanceTable } from "@/features/employee-performance/components/performance-table";

import { greeting } from "./utils";

const UNIT_LABEL: Record<string, string> = {
  tags: "Tags",
  docs: "Docs",
  bom: "BOM",
  spares: "Spares",
};
function formatUnit(unit: string | null): string {
  if (!unit) return "units";
  return UNIT_LABEL[unit] ?? unit;
}
function formatDayShort(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString([], { month: "short", day: "numeric" });
}

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
  const backlog = data?.backlog ?? [];

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

      {/* Incomplete benchmark work — submitted reports whose benchmark target
          isn't met yet (reconciled remaining qty), per employee/activity. */}
      {backlog.length > 0 && (
        <section className="mb-4">
          <h2 className="mb-3 text-base font-semibold">Incomplete benchmark work</h2>
          <Card className="overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Employee</TableHead>
                  <TableHead>Activity</TableHead>
                  <TableHead className="text-right">Remaining</TableHead>
                  <TableHead className="text-right">Day</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {backlog.map((r) => (
                  <TableRow key={`${r.employee_id}-${r.date}-${r.sub_activity_name}`}>
                    <TableCell className="font-medium">{r.employee_name}</TableCell>
                    <TableCell className="max-w-[420px]">
                      <span className="block truncate text-sm">{r.sub_activity_name}</span>
                      {r.activity_name && (
                        <span className="block truncate text-xs text-muted-foreground">
                          {r.activity_name}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <Badge variant="danger" dot>
                        {Math.round(Number(r.pending))} {formatUnit(r.benchmark_unit)}
                      </Badge>
                    </TableCell>
                    <TableCell className="tabular text-right text-sm text-muted-foreground">
                      {formatDayShort(r.date)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </section>
      )}

      {/* Employee Performance — primary section. Row click → /dashboard/employees/{id} */}
      <PerformanceTable />
    </>
  );
}
