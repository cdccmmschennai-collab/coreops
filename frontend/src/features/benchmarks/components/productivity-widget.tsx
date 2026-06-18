"use client";

import * as React from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatMinutes } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useMyAlerts } from "../hooks";
import { computeReconciliation, rowKey, type Recon } from "../reconciliation";
import type { DailyBenchmarkRow, TaskStatus, TaskStatusRow } from "../types";

const UNIT_LABEL: Record<string, string> = {
  tags: "Tags",
  docs: "Docs",
  bom: "BOM",
  spares: "Spares",
};

const DOW_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  pending: "Pending",
  due_today: "Due Today",
  completed: "Completed",
};

const TASK_STATUS_VARIANT: Record<TaskStatus, "danger" | "warning" | "success"> = {
  pending: "danger",
  due_today: "warning",
  completed: "success",
};

// Left-edge accent colour per badge variant — mirrors the badge hue so the
// row reads at a glance.
const ACCENT: Record<"danger" | "warning" | "success", string> = {
  danger: "border-l-destructive",
  warning: "border-l-warning",
  success: "border-l-success",
};

function formatUnit(unit: string | null): string {
  if (!unit) return "units";
  return UNIT_LABEL[unit] ?? unit;
}

// Parse a "YYYY-MM-DD" string as a local date (not UTC midnight) so the
// weekday / day labels can't drift a day depending on the viewer's timezone.
function parseLocal(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}
function formatDay(iso: string): string {
  return DOW_SHORT[parseLocal(iso).getDay()];
}
function formatDateShort(iso: string): string {
  const d = parseLocal(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}
function formatDateLong(iso: string): string {
  const d = parseLocal(iso);
  return `${String(d.getDate()).padStart(2, "0")}-${MONTHS[d.getMonth()]}-${d.getFullYear()}`;
}

// ── shared row pieces ─────────────────────────────────────────────────────────

// Compact date cell: inline on mobile, stacked weekday-over-date on wide rows.
function DateCell({ iso }: { iso: string }) {
  return (
    <div className="flex items-baseline gap-1.5 lg:flex-col lg:gap-0">
      <span className="text-sm font-semibold leading-tight">{formatDay(iso)}</span>
      <span className="text-xs text-muted-foreground">{formatDateShort(iso)}</span>
    </div>
  );
}

// A labelled value column (label above value). On mobile the label keeps each
// value self-describing; on wide rows the labels act as lightweight headers.
function Col({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm">{children}</div>
    </div>
  );
}

function ProgressMeter({
  actual,
  target,
  met: metProp,
}: {
  actual: number;
  target: number;
  // Optional override: when a short day has been reconciled by later excess,
  // it reads as met (full bar) even though actual < target on the day itself.
  met?: boolean;
}) {
  const ownMet = target > 0 && actual >= target;
  const met = metProp ?? ownMet;
  const notStarted = actual <= 0 && target > 0 && !met;
  const pct = met ? 100 : target > 0 ? Math.min(100, (actual / target) * 100) : 0;
  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
          {notStarted ? "Not Started" : "Progress"}
        </span>
        <span className="text-sm font-semibold tabular">
          {Math.round(actual)} / {Math.round(target)}
        </span>
      </div>
      <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-secondary">
        <div
          className={cn("h-full rounded-full transition-all", met ? "bg-success" : "bg-primary")}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// The card shell: left status accent + a responsive grid. Columns flow
// vertically on mobile and line up as a row (date | details | … ) on lg.
function RowCard({
  iso,
  variant,
  cols,
  children,
}: {
  iso: string;
  variant: "danger" | "warning" | "success";
  cols: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("rounded-lg border border-l-4 border-border bg-card", ACCENT[variant])}>
      <div className={cn("grid grid-cols-1 gap-3 p-3.5 lg:items-center lg:gap-5", cols)}>
        <DateCell iso={iso} />
        {children}
      </div>
    </div>
  );
}

// Date | Details | Hours | Progress | Pending+status
const BENCHMARK_COLS = "lg:grid-cols-[3.25rem_minmax(0,1fr)_5.5rem_13rem_auto]";

function BenchmarkCard({ row, recon }: { row: DailyBenchmarkRow; recon: Recon | undefined }) {
  const actual = Number(row.actual);
  const target = Number(row.target);
  const effectivePending = recon ? recon.effectivePending : Number(row.pending);
  const met = effectivePending <= 0;
  // Was short on the day but recovered by a later day's excess.
  const recovered = recon?.reconciled ?? false;
  const clearedBacklog = recon?.clearedBacklog ?? 0;
  const unit = formatUnit(row.benchmark_unit);

  return (
    <RowCard iso={row.date} variant={met ? "success" : "danger"} cols={BENCHMARK_COLS}>
      <div className="min-w-0 space-y-1">
        {row.project_name && (
          <div className="break-words text-sm font-medium text-foreground">{row.project_name}</div>
        )}
        {row.activity_name && (
          <div className="break-words text-xs text-muted-foreground">
            Activity: <span className="text-foreground">{row.activity_name}</span>
          </div>
        )}
        <div className="break-words text-xs text-muted-foreground">
          Sub Activity: <span className="text-foreground">{row.sub_activity_name}</span>
        </div>
        {recovered && (
          <div className="inline-block rounded bg-success/10 px-1.5 py-0.5 text-[11px] text-success">
            Backlog recovered by later excess
          </div>
        )}
        {clearedBacklog > 0 && (
          <div className="inline-block rounded bg-success/10 px-1.5 py-0.5 text-[11px] text-success">
            +{Math.round(clearedBacklog)} {unit} cleared earlier backlog
          </div>
        )}
      </div>

      <Col label="Hours">
        <span className="tabular">{formatMinutes(row.hours_minutes)}</span>
      </Col>

      <ProgressMeter actual={actual} target={target} met={met} />

      <div className="flex items-center justify-between gap-2 lg:flex-col lg:items-end lg:justify-center lg:gap-1.5">
        <Badge variant={met ? "success" : "danger"} dot>
          {met ? "Completed" : "Pending"}
        </Badge>
        <span className={cn("text-xs tabular", met ? "text-success" : "text-destructive")}>
          Pending: {Math.round(effectivePending)} {unit}
        </span>
      </div>
    </RowCard>
  );
}

// Date | Details | Hours | Due Date | status
const TASK_COLS = "lg:grid-cols-[3.25rem_minmax(0,1fr)_5.5rem_11rem_auto]";

function TaskRow({ row }: { row: TaskStatusRow }) {
  // Presentation-only: the left date is the WORK REPORT DATE — the day the
  // employee reported/worked the task — matching the Benchmark Performance
  // section, which also timelines by report date. Due Date stays visible, and
  // a completed task additionally shows "Completed On" (completed_date). This
  // does not touch filtering, which remains keyed on due_date inside the
  // current week.
  const completed = row.status === "completed";
  return (
    <RowCard iso={row.report_date} variant={TASK_STATUS_VARIANT[row.status]} cols={TASK_COLS}>
      <div className="min-w-0 space-y-1">
        {row.project_name && (
          <div className="break-words text-sm font-medium text-foreground">{row.project_name}</div>
        )}
        {row.activity_name && (
          <div className="break-words text-xs text-muted-foreground">
            Activity: <span className="text-foreground">{row.activity_name}</span>
          </div>
        )}
        <div className="break-words text-xs text-muted-foreground">
          Sub Activity: <span className="text-foreground">{row.sub_activity_name}</span>
        </div>
      </div>

      <Col label="Hours">
        <span className="tabular">{formatMinutes(row.hours_minutes)}</span>
      </Col>

      <Col label="Due Date">
        <span className="tabular">{formatDateLong(row.due_date)}</span>
        {completed && row.completed_date && (
          <div className="mt-1 text-xs text-muted-foreground">
            Completed On:{" "}
            <span className="tabular text-foreground">{formatDateLong(row.completed_date)}</span>
          </div>
        )}
      </Col>

      <div className="flex items-center justify-end gap-2 lg:flex-col lg:items-end lg:justify-center lg:gap-1.5">
        <Badge variant={TASK_STATUS_VARIANT[row.status]} dot>
          {TASK_STATUS_LABEL[row.status]}
        </Badge>
      </div>
    </RowCard>
  );
}

export function ProductivityWidget() {
  const [expanded, setExpanded] = React.useState(false);
  const { data, isLoading } = useMyAlerts();

  const daily = data?.daily ?? [];
  const tasks = data?.tasks ?? [];
  const reconMap = React.useMemo(() => computeReconciliation(daily), [daily]);

  if (isLoading) {
    return <Skeleton className="mb-4 h-[60px] w-full" />;
  }

  const productivity = data?.summary.productivity_pct;
  const productivityLabel = productivity != null ? `${Number(productivity).toFixed(0)}%` : "—";

  // Completed/pending counts honour reconciliation — a day cleared by a later
  // day's excess counts as Completed, matching its row badge.
  const totalBenchmarks = daily.length;
  const completedBenchmarks = daily.filter(
    (r) => (reconMap.get(rowKey(r))?.effectivePending ?? Number(r.pending)) <= 0,
  ).length;
  const pendingBenchmarks = totalBenchmarks - completedBenchmarks;

  return (
    <Card className="mb-4 overflow-hidden">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 px-5 py-3.5 text-left"
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="text-base font-semibold">Productivity This Week</span>
        <span className="flex items-center gap-2">
          <span className="text-base font-semibold tabular">{productivityLabel}</span>
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </span>
      </button>

      {expanded && (
        <CardContent className="border-t border-border bg-muted/30 p-4">
          {/* Benchmark performance — full-width rows, stacked vertically */}
          <section>
            <h3 className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Benchmark performance
            </h3>
            {daily.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border py-6 text-center text-sm text-muted-foreground">
                No benchmark activity this week.
              </p>
            ) : (
              <div className="space-y-2.5">
                {daily.map((row) => (
                  <BenchmarkCard key={rowKey(row)} row={row} recon={reconMap.get(rowKey(row))} />
                ))}
              </div>
            )}
          </section>

          {/* Pending tasks (this week) — directly below benchmark performance */}
          <section className="mt-6 border-t border-border pt-4">
            <h3 className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Pending Tasks (This Week)
            </h3>
            {tasks.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border py-6 text-center text-sm text-muted-foreground">
                No tasks due this week.
              </p>
            ) : (
              <div className="space-y-2.5">
                {tasks.map((row) => <TaskRow key={row.work_report_task_id} row={row} />)}
              </div>
            )}
          </section>

          <div className="mt-6 grid grid-cols-2 gap-3 border-t border-border pt-4 sm:grid-cols-4">
            <div className="text-center">
              <div className="text-lg font-semibold tabular">{totalBenchmarks}</div>
              <div className="text-xs text-muted-foreground">Total Benchmarks</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-semibold tabular text-success">{completedBenchmarks}</div>
              <div className="text-xs text-muted-foreground">Completed</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-semibold tabular text-destructive">{pendingBenchmarks}</div>
              <div className="text-xs text-muted-foreground">Pending</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-semibold tabular">{productivityLabel}</div>
              <div className="text-xs text-muted-foreground">Productivity %</div>
            </div>
          </div>
        </CardContent>
      )}
    </Card>
  );
}
