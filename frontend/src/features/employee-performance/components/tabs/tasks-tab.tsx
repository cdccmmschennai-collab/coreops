"use client";

import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Kpi, KpiGrid } from "@/components/ui/kpi";
import { Skeleton } from "@/components/ui/skeleton";

import type { WorkReportTask } from "@/features/work-reports/types";

import { useEmployeeWeekReports } from "../../hooks";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function formatDateShort(iso: string | null): string | null {
  if (!iso) return null;
  const [y, m, d] = iso.split("-").map(Number);
  return `${new Date(y, m - 1, d).getDate()} ${MONTHS[m - 1]}`;
}

const COUNT_LABEL: Record<string, string> = {
  tags: "Tags", docs: "Docs", bom: "BOM", spares: "Spares",
};

/** The numeric value of the ONE count this sub-activity's benchmark tracks, or
 * null when the row tracks no benchmark field. */
function relevantCountValue(t: WorkReportTask): number | null {
  const field = t.relevant_count_field_snapshot;
  if (!field) return null;
  return (
    field === "tags" ? t.tags_count
    : field === "docs" ? t.docs_count
    : field === "bom" ? t.bom_count
    : field === "spares" ? t.spares_count
    : null
  );
}

/** Only the ONE count that belongs to this sub-activity (the field its benchmark
 * tracks), e.g. "100 Tags" — never all four. Null for rows with no tracked field. */
function relevantCount(t: WorkReportTask): string | null {
  const field = t.relevant_count_field_snapshot;
  if (!field) return null;
  return `${relevantCountValue(t) ?? 0} ${COUNT_LABEL[field] ?? field}`;
}

/** A NUMERIC benchmark row is "met" when its tracked count reaches the target —
 * mirrors the backend rule (target > 0 and actual >= target). Returns null for
 * non-benchmark (task-based) rows, which use the manual is_completed flag. */
function benchmarkMet(t: WorkReportTask): boolean | null {
  const target = Number(t.benchmark_value_snapshot ?? 0);
  if (!t.relevant_count_field_snapshot || !(target > 0)) return null;
  return (relevantCountValue(t) ?? 0) >= target;
}

interface TaskItem {
  id: string;
  activity: string | null;
  title: string;
  projectCode: string | null;
  date: string | null;
  count: string | null;
  status: "completed" | "overdue" | "pending";
}

// Layer 3, tab 4 — this week's tasks (work-report task rows) with counts.
export function TasksTab({ employeeId }: { employeeId: string }) {
  const { data, isLoading } = useEmployeeWeekReports(employeeId);

  const tasks = React.useMemo<TaskItem[]>(() => {
    const out: TaskItem[] = [];
    for (const report of data?.items ?? []) {
      for (const t of report.tasks) {
        // NUMERIC benchmark rows are "completed" when the target is met; only
        // task-based rows (benchmarkMet === null) fall back to the manual flag.
        const met = benchmarkMet(t);
        const status: TaskItem["status"] =
          met === true || (met === null && t.is_completed)
            ? "completed"
            : met === null && t.is_overdue
              ? "overdue"
              : "pending";
        out.push({
          id: t.id,
          activity: t.activity_name ?? null,
          title: t.sub_activity_name || t.description || "Activity",
          projectCode: t.project_code ?? null,
          date: report.report_date,
          count: relevantCount(t),
          status,
        });
      }
    }
    return out;
  }, [data]);

  if (isLoading) return <Skeleton className="h-48 w-full" />;

  const completed = tasks.filter((t) => t.status === "completed").length;
  const overdue = tasks.filter((t) => t.status === "overdue").length;
  const pending = tasks.filter((t) => t.status === "pending").length;

  return (
    <div className="space-y-4">
      <KpiGrid>
        <Kpi label="Total activities" value={String(tasks.length)} />
        <Kpi label="Completed" value={String(completed)} />
        <Kpi label="Pending" value={String(pending)} />
        <Kpi label="Overdue" value={String(overdue)} />
      </KpiGrid>

      <Card className="overflow-hidden">
        <CardHeader className="border-b border-border px-5 py-3.5">
          <CardTitle className="text-base">Activities this week</CardTitle>
        </CardHeader>
        <CardContent className="p-2">
          {tasks.length === 0 ? (
            <p className="px-3 py-8 text-center text-sm text-muted-foreground">
              No activities logged this week.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {tasks.map((t) => (
                <li key={t.id} className="flex items-center justify-between gap-3 px-2.5 py-2.5">
                  <div className="min-w-0">
                    <p className="text-sm text-foreground [overflow-wrap:anywhere]">
                      {t.activity && (
                        <span className="font-normal text-muted-foreground">{t.activity} / </span>
                      )}
                      <span className="font-bold">{t.title}</span>
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {[t.projectCode, formatDateShort(t.date), t.count].filter(Boolean).join(" · ")}
                    </p>
                  </div>
                  <Badge
                    variant={
                      t.status === "completed" ? "success" : t.status === "overdue" ? "danger" : "warning"
                    }
                    dot
                  >
                    {t.status === "completed" ? "Completed" : t.status === "overdue" ? "Overdue" : "Pending"}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
