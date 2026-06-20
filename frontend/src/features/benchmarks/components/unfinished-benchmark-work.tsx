"use client";

import * as React from "react";
import { AlertTriangle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { useMyAlerts } from "../hooks";
import { computeReconciliation, rowKey } from "../reconciliation";

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

/**
 * Always-visible block listing this week's benchmark activities that are
 * SUBMITTED but still INCOMPLETE (actual < target), after backlog recovery —
 * i.e. work the employee can still continue on a later day. Surfaces the
 * remaining quantity per activity. Renders nothing when there's no unfinished
 * work, so a fully-caught-up employee sees a clean dashboard.
 */
export function UnfinishedBenchmarkWork() {
  const { data, isLoading } = useMyAlerts();
  const daily = data?.daily ?? [];
  const recon = React.useMemo(() => computeReconciliation(daily), [daily]);

  if (isLoading) return null;

  const items = daily
    .map((row) => ({
      row,
      remaining: recon.get(rowKey(row))?.effectivePending ?? Number(row.pending),
    }))
    .filter((x) => x.remaining > 0)
    .sort((a, b) => b.remaining - a.remaining);

  if (items.length === 0) return null;

  return (
    <Card className="mb-4 overflow-hidden border-l-4 border-l-destructive">
      <CardHeader className="flex-row items-center justify-between gap-3 space-y-0 border-b border-border px-5 py-3.5">
        <CardTitle className="flex items-center gap-2 text-base">
          <AlertTriangle className="h-4 w-4 text-destructive" />
          Unfinished benchmark work
        </CardTitle>
        <span className="text-xs text-muted-foreground">
          Exceed a day&apos;s target to clear earlier backlog
        </span>
      </CardHeader>
      <CardContent className="p-2">
        <ul className="divide-y divide-border">
          {items.map(({ row, remaining }) => (
            <li
              key={rowKey(row)}
              className="flex items-center justify-between gap-3 px-3 py-2.5"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-foreground">
                  {row.sub_activity_name}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {row.activity_name ? `${row.activity_name} · ` : ""}
                  {row.project_name ?? "—"}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span className="tabular text-xs text-muted-foreground">
                  {Math.round(Number(row.actual))} / {Math.round(Number(row.target))}
                </span>
                <Badge variant="danger" dot>
                  {Math.round(remaining)} {formatUnit(row.benchmark_unit)} left
                </Badge>
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
