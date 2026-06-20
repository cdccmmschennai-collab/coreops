"use client";

import { Kpi, KpiGrid } from "@/components/ui/kpi";
import { Skeleton } from "@/components/ui/skeleton";
import { formatMinutes } from "@/lib/format";

import { useEmployeeOverview } from "../hooks";

/**
 * The single Overview surface — rendered by BOTH the Layer 2 drawer and the
 * Layer 3 Overview tab. One hook, one component: the two layers can never
 * diverge. All numbers come from GET /benchmarks/employees/{id}/overview; no
 * metric is computed here.
 */
export function EmployeeOverview({ employeeId }: { employeeId: string }) {
  const { data, isLoading, isError } = useEmployeeOverview(employeeId);

  if (isLoading || !data) {
    return <Skeleton className="h-28 w-full" />;
  }
  if (isError) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        Could not load overview.
      </p>
    );
  }

  const productivity =
    data.productivity_pct != null ? `${Number(data.productivity_pct).toFixed(0)}%` : "—";

  return (
    <KpiGrid>
      <Kpi label="Productivity" value={productivity} />
      <Kpi label="Hours this week" value={formatMinutes(data.hours_this_week_minutes)} />
      <Kpi label="Completed benchmarks" value={String(data.completed_benchmarks)} />
      <Kpi label="Pending" value={String(data.pending_benchmarks)} />
      <Kpi label="Overdue" value={String(data.overdue_activities)} />
    </KpiGrid>
  );
}
