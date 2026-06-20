"use client";

import * as React from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

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

const DOW_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Parse "YYYY-MM-DD" as a LOCAL date (not UTC) so weekday / day-diff labels
// can't drift a day depending on the viewer's timezone.
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
function todayMidnight(): Date {
  const n = new Date();
  return new Date(n.getFullYear(), n.getMonth(), n.getDate());
}
// Whole-day difference between a due date and today (local). >0 future, 0 today,
// <0 past.
function dueDayDiff(iso: string): number {
  return Math.round((parseLocal(iso).getTime() - todayMidnight().getTime()) / 86_400_000);
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

// Task-based relative status — actionable wording only (no raw due/completed
// dates): "Due Today" / "Due in N Days" while on time, "N Days Overdue" once
// the due date has passed.
function taskStatus(due: string): { status: Status; detail: string } {
  const diff = dueDayDiff(due);
  if (diff > 0) return { status: "in_progress", detail: diff === 1 ? "Due in 1 Day" : `Due in ${diff} Days` };
  if (diff === 0) return { status: "in_progress", detail: "Due Today" };
  const n = -diff;
  return { status: "overdue", detail: n === 1 ? "1 Day Overdue" : `${n} Days Overdue` };
}

function StatusPill({ status }: { status: Status }) {
  return status === "overdue" ? (
    <Badge variant="danger" dot>
      Overdue
    </Badge>
  ) : (
    <Badge variant="info" dot>
      In Progress
    </Badge>
  );
}

/**
 * "Benchmark Activities" — the employee's single, work-focused list of open
 * benchmark work for the current week. One card, one table, no analytics:
 *
 *   NUMERIC rows     — reconciled backlog still incomplete (effective_pending
 *                      > 0 after later-day surplus clears earlier deficits), so
 *                      a row disappears automatically once caught up. Always
 *                      "In Progress"; Details = "{actual} / {target} • {n} left".
 *   TASK_BASED rows  — only INCOMPLETE tasks (a completed task is dropped
 *                      immediately). Relative status: "In Progress" with "Due
 *                      in N Days" while on time, "Overdue" with "N Days Overdue"
 *                      once past due.
 *
 * Both sources are current-week-only and reset every Monday with the ledger.
 * Renders an empty-state message (table hidden) when nothing needs attention.
 */
export function BenchmarkActivities() {
  const { data, isLoading } = useMyAlerts();
  const daily = data?.daily ?? [];
  const tasks = data?.tasks ?? [];
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

    // TASK_BASED — incomplete only (completed tasks are dropped), most overdue
    // first then soonest-due.
    const taskItems: ActivityItem[] = tasks
      .filter((t) => t.status !== "completed")
      .sort((a, b) => a.due_date.localeCompare(b.due_date))
      .map((t) => {
        const { status, detail } = taskStatus(t.due_date);
        return {
          id: t.work_report_task_id,
          date: t.report_date,
          projectCode: t.project_code,
          activity: t.activity_name,
          subActivity: t.sub_activity_name,
          status,
          details: <span className="font-medium">{detail}</span>,
        };
      });

    return [...numeric, ...taskItems];
  }, [daily, tasks, recon]);

  // Clicking the header row collapses / expands the whole activities table.
  // Collapsed by default — the employee opens it to view the list.
  const [collapsed, setCollapsed] = React.useState(true);

  // Measure the content so expand/collapse animates to an exact pixel height.
  // (Animating a real px height is smooth; the grid-rows `0fr→1fr` trick
  // sub-pixel-rounds each frame, which is what made it visibly "shake".)
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const [contentHeight, setContentHeight] = React.useState<number>();
  React.useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const measure = () => setContentHeight(el.offsetHeight);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [items]);

  if (isLoading) return null;

  const inProgressCount = items.filter((i) => i.status === "in_progress").length;
  const overdueCount = items.filter((i) => i.status === "overdue").length;

  return (
    <Card className="mb-4 overflow-hidden">
      <CardHeader
        className={`flex-row items-center justify-between gap-3 space-y-0 px-5 py-3.5 ${
          items.length > 0 && !collapsed ? "border-b border-border" : ""
        }`}
        role={items.length > 0 ? "button" : undefined}
        tabIndex={items.length > 0 ? 0 : undefined}
        aria-expanded={items.length > 0 ? !collapsed : undefined}
        onClick={items.length > 0 ? () => setCollapsed((c) => !c) : undefined}
        onKeyDown={
          items.length > 0
            ? (e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setCollapsed((c) => !c);
                }
              }
            : undefined
        }
        style={items.length > 0 ? { cursor: "pointer" } : undefined}
      >
        <CardTitle className="flex items-center gap-1.5 text-base">
          {items.length > 0 &&
            (collapsed ? (
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            ) : (
              <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
            ))}
          Benchmark Activities ({items.length})
        </CardTitle>
        {items.length > 0 && (
          <span className="text-xs text-muted-foreground">
            <span className="text-primary">{inProgressCount} In Progress</span>
            <span className="px-1.5">•</span>
            <span className="text-destructive">{overdueCount} Overdue</span>
          </span>
        )}
      </CardHeader>

      {items.length === 0 ? (
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          No benchmark activities requiring attention.
        </CardContent>
      ) : (
        <div
          className="overflow-hidden transition-[height] duration-300 ease-out motion-reduce:transition-none"
          style={{ height: collapsed ? 0 : contentHeight }}
        >
          <div ref={scrollRef} className="max-h-[28rem] overflow-auto">
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
        </div>
      )}
    </Card>
  );
}
