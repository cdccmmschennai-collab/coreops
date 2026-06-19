"use client";

import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Kpi, KpiGrid } from "@/components/ui/kpi";
import { Skeleton } from "@/components/ui/skeleton";
import { formatMinutes } from "@/lib/format";

import { useEmployeeWeekReports } from "../../hooks";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function formatDateShort(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-").map(Number);
  return `${new Date(y, m - 1, d).getDate()} ${MONTHS[m - 1]}`;
}

interface TaskItem {
  id: string;
  title: string;
  project: string | null;
  minutes: number;
  dueDate: string | null;
  status: "completed" | "overdue" | "pending";
}

// Layer 3, tab 4 — this week's tasks (work-report task rows) with counts.
export function TasksTab({ employeeId }: { employeeId: string }) {
  const { data, isLoading } = useEmployeeWeekReports(employeeId);

  const tasks = React.useMemo<TaskItem[]>(() => {
    const out: TaskItem[] = [];
    for (const report of data?.items ?? []) {
      for (const t of report.tasks) {
        const status: TaskItem["status"] = t.is_completed
          ? "completed"
          : t.is_overdue
            ? "overdue"
            : "pending";
        out.push({
          id: t.id,
          title: t.task_title || t.sub_activity_name || t.description || "Task",
          project: t.project_name ?? null,
          minutes: t.minutes_spent ?? 0,
          dueDate: t.due_date ?? null,
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
        <Kpi label="Total tasks" value={String(tasks.length)} />
        <Kpi label="Completed" value={String(completed)} />
        <Kpi label="Pending" value={String(pending)} />
        <Kpi label="Overdue" value={String(overdue)} />
      </KpiGrid>

      <Card className="overflow-hidden">
        <CardHeader className="border-b border-border px-5 py-3.5">
          <CardTitle className="text-base">Tasks this week</CardTitle>
        </CardHeader>
        <CardContent className="p-2">
          {tasks.length === 0 ? (
            <p className="px-3 py-8 text-center text-sm text-muted-foreground">
              No tasks logged this week.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {tasks.map((t) => (
                <li key={t.id} className="flex items-center justify-between gap-3 px-2.5 py-2.5">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-foreground">{t.title}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {t.project ?? "—"} · {formatMinutes(t.minutes)}
                      {t.dueDate && ` · due ${formatDateShort(t.dueDate)}`}
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
