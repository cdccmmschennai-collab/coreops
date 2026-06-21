"use client";

import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { computeReconciliation, rowKey } from "@/features/benchmarks/reconciliation";

import { useEmployeeBenchmarks } from "../../hooks";

const UNIT_LABEL: Record<string, string> = {
  tags: "Tags",
  docs: "Docs",
  bom: "BOM",
  spares: "Spares",
};
const DOW_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatUnit(unit: string | null): string {
  return unit ? UNIT_LABEL[unit] ?? unit : "units";
}
// Parse "YYYY-MM-DD" as a LOCAL date so weekday labels can't drift a day by tz.
function parseLocal(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}
function formatDateShort(iso: string): string {
  const d = parseLocal(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}
function formatDay(iso: string): string {
  return DOW_SHORT[parseLocal(iso).getDay()];
}

type Status = "in_progress" | "overdue";

interface ActivityItem {
  id: string;
  date: string;
  projectCode: string | null;
  activity: string | null;
  subActivity: string;
  status: Status;
  details: React.ReactNode;
}

function StatusPill({ status }: { status: Status }) {
  // Per spec: blue "In Progress" (numeric backlog), orange "Overdue" (task-based).
  return status === "overdue" ? (
    <Badge variant="warning" dot>
      Overdue
    </Badge>
  ) : (
    <Badge variant="info" dot>
      In Progress
    </Badge>
  );
}

/**
 * Layer 3, Benchmarks tab — the single source of truth for one employee's open
 * benchmark work this week. Two row kinds, both from the SAME backend service
 * and reconciliation the PM dashboard / employee widget use (no new math):
 *
 *   IN PROGRESS — NUMERIC backlog still short after reconciliation
 *                 (effectivePending > 0; later-day surplus pays down earlier
 *                 deficits, so a caught-up day drops out). Details: actual /
 *                 target • N Left.
 *   OVERDUE     — TASK_BASED rows past their due date and not completed.
 *                 Details: "N Days Overdue" (the due date itself is never shown).
 */
export function BenchmarksTab({ employeeId }: { employeeId: string }) {
  const { data, isLoading } = useEmployeeBenchmarks(employeeId);

  const daily = data?.daily ?? [];
  const overdue = data?.overdue ?? [];
  const recon = React.useMemo(() => computeReconciliation(daily), [daily]);

  const items: ActivityItem[] = React.useMemo(() => {
    // NUMERIC — reconciled backlog still pending, oldest first.
    const numeric: ActivityItem[] = daily
      .map((row) => ({
        row,
        remaining: recon.get(rowKey(row))?.effectivePending ?? Number(row.pending),
      }))
      .filter((x) => x.remaining > 0)
      .sort((a, b) => a.row.date.localeCompare(b.row.date) || b.remaining - a.remaining)
      .map(({ row, remaining }) => ({
        id: rowKey(row),
        date: row.date,
        projectCode: row.project_code,
        activity: row.activity_name,
        subActivity: row.sub_activity_name,
        status: "in_progress" as Status,
        details: (
          <span>
            <span className="tabular text-muted-foreground">
              {Math.round(Number(row.actual))} / {Math.round(Number(row.target))}
            </span>
            <span className="px-1.5 text-muted-foreground">•</span>
            <span className="font-medium">
              {Math.round(remaining)} {formatUnit(row.benchmark_unit)} Left
            </span>
          </span>
        ),
      }));

    // TASK_BASED — overdue only, most overdue first.
    const overdueItems: ActivityItem[] = [...overdue]
      .sort((a, b) => b.days_overdue - a.days_overdue)
      .map((r) => ({
        id: r.work_report_task_id,
        date: r.report_date,
        projectCode: r.project_code,
        activity: r.activity_name,
        subActivity: r.sub_activity_name,
        status: "overdue" as Status,
        details: (
          <span className="font-medium">
            {r.days_overdue === 1 ? "1 Day Overdue" : `${r.days_overdue} Days Overdue`}
          </span>
        ),
      }));

    return [...numeric, ...overdueItems];
  }, [daily, overdue, recon]);

  if (isLoading) return <Skeleton className="h-48 w-full" />;

  const inProgressCount = items.filter((i) => i.status === "in_progress").length;
  const overdueCount = items.filter((i) => i.status === "overdue").length;

  return (
    <Card className="overflow-hidden">
      <CardHeader
        className={`flex-row items-center justify-between gap-3 space-y-0 px-5 py-3.5 ${
          items.length > 0 ? "border-b border-border" : ""
        }`}
      >
        <CardTitle className="text-base">Benchmark Activities ({items.length})</CardTitle>
        {items.length > 0 && (
          <span className="text-xs text-muted-foreground">
            <span className="text-primary">{inProgressCount} In Progress</span>
            <span className="px-1.5">•</span>
            <span className="text-warning">{overdueCount} Overdue</span>
          </span>
        )}
      </CardHeader>

      {items.length === 0 ? (
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          No benchmark activities requiring attention.
        </CardContent>
      ) : (
        <div className="max-h-[28rem] overflow-auto">
          <table className="w-full caption-bottom text-sm">
            <TableHeader className="[&_th]:sticky [&_th]:top-0 [&_th]:z-10 [&_th]:bg-card [&_th]:shadow-[inset_0_-1px_0_hsl(var(--border))]">
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-20">Date</TableHead>
                <TableHead className="w-28">Project</TableHead>
                <TableHead className="w-28">Activity</TableHead>
                <TableHead>Sub Activity</TableHead>
                <TableHead className="w-28">Status</TableHead>
                <TableHead className="w-44">Details</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="align-top">
                    <span className="font-medium tabular">{formatDateShort(item.date)}</span>
                    <span className="ml-1.5 text-xs text-muted-foreground">{formatDay(item.date)}</span>
                  </TableCell>
                  <TableCell className="align-top font-medium tabular">
                    {item.projectCode ?? "—"}
                  </TableCell>
                  <TableCell className="align-top text-muted-foreground">
                    {item.activity ?? "—"}
                  </TableCell>
                  <TableCell
                    className="align-top font-medium text-foreground [overflow-wrap:anywhere]"
                    title={item.subActivity}
                  >
                    <span className="line-clamp-2">{item.subActivity}</span>
                  </TableCell>
                  <TableCell className="align-top">
                    <StatusPill status={item.status} />
                  </TableCell>
                  <TableCell className="align-top">{item.details}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </table>
        </div>
      )}
    </Card>
  );
}
