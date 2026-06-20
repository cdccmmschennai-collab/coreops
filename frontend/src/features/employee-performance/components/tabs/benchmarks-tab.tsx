"use client";

import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { computeReconciliation, rowKey } from "@/features/benchmarks/reconciliation";
import { formatInt } from "@/lib/format";

import { useEmployeeBenchmarks } from "../../hooks";

const UNIT_LABEL: Record<string, string> = {
  tags: "Tags",
  docs: "Docs",
  bom: "BOM",
  spares: "Spares",
};
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatUnit(unit: string | null): string {
  return unit ? UNIT_LABEL[unit] ?? unit : "units";
}
function formatDateShort(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${new Date(y, m - 1, d).getDate()} ${MONTHS[m - 1]}`;
}

/**
 * Layer 3, tab 2 — per-employee benchmarks for the current week. Pulls the full
 * daily ledger and runs the SAME computeReconciliation the employee's own widget
 * uses, so backlog reflects what's *still* outstanding (later-day surplus pays
 * down earlier deficits) — not the raw historical deficit.
 */
export function BenchmarksTab({ employeeId }: { employeeId: string }) {
  const { data, isLoading } = useEmployeeBenchmarks(employeeId);

  const daily = data?.daily ?? [];
  const overdue = data?.overdue ?? [];
  const recon = React.useMemo(() => computeReconciliation(daily), [daily]);

  // Only days still short after reconciliation appear in the backlog.
  const backlog = daily
    .map((row) => ({ row, pending: recon.get(rowKey(row))?.effectivePending ?? Number(row.pending) }))
    .filter((x) => x.pending > 0);

  if (isLoading) return <Skeleton className="h-48 w-full" />;

  return (
    <div className="space-y-4">
      <Card className="overflow-hidden">
        <CardHeader className="border-b border-border px-5 py-3.5">
          <CardTitle className="text-base">Benchmark backlog (this week)</CardTitle>
        </CardHeader>
        <CardContent className="p-2">
          {backlog.length === 0 ? (
            <p className="px-3 py-8 text-center text-sm text-muted-foreground">
              No outstanding benchmarks this week.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {backlog.map(({ row, pending }) => (
                <li key={rowKey(row)} className="px-2.5 py-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm font-medium text-foreground">
                      {row.sub_activity_name}
                    </p>
                    <span className="shrink-0 text-xs tabular text-muted-foreground">
                      {formatDateShort(row.date)}
                    </span>
                  </div>
                  <p className="text-xs text-destructive">
                    {formatInt(pending)} {formatUnit(row.benchmark_unit)} pending
                  </p>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card className="overflow-hidden">
        <CardHeader className="border-b border-border px-5 py-3.5">
          <CardTitle className="text-base">Overdue activities</CardTitle>
        </CardHeader>
        <CardContent className="p-2">
          {overdue.length === 0 ? (
            <p className="px-3 py-8 text-center text-sm text-muted-foreground">
              No overdue activities.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {overdue.map((r) => (
                <li key={r.work_report_task_id} className="px-2.5 py-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm font-medium text-foreground">
                      {r.sub_activity_name}
                    </p>
                    <Badge variant="danger">{r.days_overdue}d overdue</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">due {formatDateShort(r.due_date)}</p>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
