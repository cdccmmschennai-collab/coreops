"use client";

import * as React from "react";

import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Kpi, KpiGrid } from "@/components/ui/kpi";
import { Skeleton } from "@/components/ui/skeleton";
import { PreviewBanner } from "@/features/attendance/components/preview-banner";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { useProjectOptions } from "@/features/work-reports/project-options";
import { useWorkReportList } from "@/features/work-reports/hooks";
import { formatMinutes } from "@/lib/format";
import type { WorkReport } from "@/features/work-reports/types";

import {
  BurnBars,
  ChartLegend,
  DonutChart,
  Heatmap,
  LineChart,
  StackedBarsPreview,
  type BurnEntry,
  type HeatmapRow,
} from "./charts";

// ── date helpers ──────────────────────────────────────────────────────────────

function pad(n: number) { return String(n).padStart(2, "0"); }

function isoDate(d: Date) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** ISO date N weeks ago from today. */
function weeksAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n * 7);
  return isoDate(d);
}

/** ISO-week label "wN" for a date string (yyyy-mm-dd). */
function weekLabel(iso: string): string {
  const d   = new Date(iso);
  const jan1 = new Date(d.getFullYear(), 0, 1);
  const wk  = Math.ceil(((d.getTime() - jan1.getTime()) / 86400000 + jan1.getDay() + 1) / 7);
  return `w${wk}`;
}

/** Monday of the week containing the given date. */
function weekOf(iso: string): string {
  const d   = new Date(iso);
  const dow = d.getDay();
  d.setDate(d.getDate() - (dow === 0 ? 6 : dow - 1));
  return isoDate(d);
}

// ── aggregation helpers ───────────────────────────────────────────────────────

function aggregateByProject(reports: WorkReport[]): Map<string, number> {
  const map = new Map<string, number>();
  for (const r of reports) {
    for (const t of r.tasks) {
      map.set(t.project_id, (map.get(t.project_id) ?? 0) + (t.minutes_spent ?? 0));
    }
  }
  return map;
}

/** Returns on-time rate per week (approved / total non-draft) as % for last N weeks. */
function weeklyOnTimeRate(reports: WorkReport[], weeks: number): { rates: number[]; labels: string[] } {
  const buckets = new Map<string, { approved: number; total: number }>();
  for (const r of reports) {
    if (r.status === "draft") continue;
    const wk = weekOf(r.report_date);
    const b  = buckets.get(wk) ?? { approved: 0, total: 0 };
    b.total++;
    if (r.status === "approved") b.approved++;
    buckets.set(wk, b);
  }
  const sorted = [...buckets.entries()].sort(([a], [b]) => a.localeCompare(b)).slice(-weeks);
  return {
    rates:  sorted.map(([, b]) => b.total > 0 ? Math.round((b.approved / b.total) * 100) : 0),
    labels: sorted.map(([wk]) => weekLabel(wk)),
  };
}

/** Builds heatmap rows: per-employee, per-week total minutes for last N weeks. */
function buildHeatmap(
  reports: WorkReport[],
  weeks: number,
  empById: Map<string, string>,
): { rows: HeatmapRow[]; weekLabels: string[] } {
  // Collect distinct weeks (last N)
  const today   = new Date();
  const weekStarts: string[] = [];
  for (let i = weeks - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i * 7 - (today.getDay() === 0 ? 6 : today.getDay() - 1));
    weekStarts.push(isoDate(d));
  }
  const wkLabel = weekStarts.map(weekLabel);

  // bucket[employeeId][weekIdx] = minutes
  const bucket = new Map<string, number[]>();
  for (const r of reports) {
    if (r.status === "draft") continue;
    const wk    = weekOf(r.report_date);
    const wkIdx = weekStarts.findIndex((ws) => ws === wk);
    if (wkIdx < 0) continue;
    const emp = bucket.get(r.employee_id) ?? Array(weeks).fill(0);
    emp[wkIdx] += r.total_minutes;
    bucket.set(r.employee_id, emp);
  }

  const rows: HeatmapRow[] = [...bucket.entries()]
    .map(([eid, wks]) => ({
      name:  empById.get(eid) ?? eid.slice(0, 8),
      weeks: wks,
    }))
    .sort((a, b) => a.name.localeCompare(b.name))
    .slice(0, 10); // max 10 rows for readability

  return { rows, weekLabels: wkLabel };
}

// ── view ──────────────────────────────────────────────────────────────────────

export function AnalyticsView() {
  const from = weeksAgo(8); // last 8 weeks
  const to   = isoDate(new Date());

  // Fetch up to 200 reports for the analytics window (all employees, admin/manager scoped by backend)
  const reportsQ = useWorkReportList({
    employee_id: "",
    project_id: "",
    status: "",
    from,
    to,
    limit: 200,
    offset: 0,
  });
  const { byId: projById } = useProjectOptions();
  const { byId: empById  } = useEmployeeOptions();

  const reports = reportsQ.data?.items ?? [];
  const total   = reportsQ.data?.total ?? 0;
  const loading = reportsQ.isLoading;

  // ── KPI computations ───────────────────────────────────────────────────────
  const nonDraft     = reports.filter((r) => r.status !== "draft");
  const totalHours   = reports.reduce((s, r) => s + r.total_minutes, 0);
  const approved     = reports.filter((r) => r.status === "approved").length;
  const onTimeRate   = nonDraft.length > 0 ? Math.round((approved / nonDraft.length) * 100) : 0;
  const pendingCount = reports.filter((r) => r.status === "submitted").length;

  // ── project burn (real) ────────────────────────────────────────────────────
  const projMinutes = aggregateByProject(reports);
  const burnEntries: BurnEntry[] = [...projMinutes.entries()]
    .map(([pid, minutes]) => ({
      name:      projById.get(pid) ?? "Unknown project",
      allocated: 9600, // 160h — placeholder allocated (no budget field yet)
      logged:    minutes,
    }))
    .sort((a, b) => b.logged - a.logged)
    .slice(0, 6);

  // ── on-time line (real) ────────────────────────────────────────────────────
  const { rates: onTimeRates, labels: wkLabels } = React.useMemo(
    () => weeklyOnTimeRate(reports, 8),
    [reports],
  );

  // ── heatmap (real) ────────────────────────────────────────────────────────
  const { rows: heatmapRows, weekLabels: heatWeeks } = React.useMemo(
    () => buildHeatmap(reports, 8, empById),
    [reports, empById],
  );

  // ── category donut (preview — no category in tasks yet) ───────────────────
  const previewSlices = [
    { label: "Development", value: 58 },
    { label: "Reviews",     value: 18 },
    { label: "Meetings",    value: 14 },
    { label: "Planning",    value: 10 },
  ];

  return (
    <>
      <PageHeader
        title="Analytics"
        subtitle="Work report and attendance aggregates for the last 8 weeks."
      />

      {/* KPIs */}
      <KpiGrid>
        {loading
          ? Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="rounded-lg border border-border bg-card p-4">
                <Skeleton className="h-4 w-24 mb-2" />
                <Skeleton className="h-7 w-16" />
              </div>
            ))
          : <>
              <Kpi label="Reports submitted" value={String(nonDraft.length)}
                delta={total > 200 ? { dir: "up", text: `${total} total` } : undefined} />
              <Kpi label="Hours logged" value={formatMinutes(totalHours)} />
              <Kpi label="On-time rate"  value={nonDraft.length > 0 ? `${onTimeRate}%` : "—"} />
              <Kpi label="Pending review" value={String(pendingCount)} />
            </>
        }
      </KpiGrid>

      {/* row 1: stacked bars (preview) + donut (preview) */}
      <div className="mb-4 grid gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader className="border-b border-border px-5 py-3.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle className="text-base">Hours by category</CardTitle>
              <ChartLegend items={[
                { color: "hsl(var(--primary))", label: "Development" },
                { color: "#8b5cf6",             label: "Reviews" },
                { color: "#10b981",             label: "Meetings" },
                { color: "#f59e0b",             label: "Planning" },
              ]} />
            </div>
          </CardHeader>
          <CardContent className="px-5 pb-4 pt-3">
            <PreviewBanner>tasks have no category field yet — distribution is representative sample data.</PreviewBanner>
            <StackedBarsPreview />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b border-border px-5 py-3.5">
            <CardTitle className="text-base">Hours by category — total</CardTitle>
          </CardHeader>
          <CardContent className="px-5 pb-4 pt-3">
            <PreviewBanner>sample data until category field exists.</PreviewBanner>
            <DonutChart slices={previewSlices} total="—" />
          </CardContent>
        </Card>
      </div>

      {/* row 2: project burn (real) + on-time line (real) */}
      <div className="mb-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="border-b border-border px-5 py-3.5">
            <div className="flex items-baseline justify-between">
              <CardTitle className="text-base">Project hours logged</CardTitle>
              <span className="text-xs text-muted-foreground">last 8 weeks</span>
            </div>
          </CardHeader>
          <CardContent className="px-5 pb-4 pt-4">
            {loading
              ? <Skeleton className="h-[200px] w-full" />
              : <BurnBars entries={burnEntries} />
            }
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b border-border px-5 py-3.5">
            <div className="flex items-baseline justify-between">
              <CardTitle className="text-base">On-time submission rate</CardTitle>
              <span className="text-xs text-muted-foreground">trailing 8 weeks</span>
            </div>
          </CardHeader>
          <CardContent className="px-5 pb-4 pt-4">
            {loading
              ? <Skeleton className="h-[148px] w-full" />
              : onTimeRates.length < 2
                ? <p className="py-8 text-center text-sm text-muted-foreground">Not enough data yet.</p>
                : <LineChart data={onTimeRates} labels={wkLabels} />
            }
          </CardContent>
        </Card>
      </div>

      {/* row 3: workload heatmap (real) */}
      <Card>
        <CardHeader className="border-b border-border px-5 py-3.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle className="text-base">Workload heatmap</CardTitle>
            <span className="text-xs text-muted-foreground">hours per person · last 8 weeks</span>
          </div>
        </CardHeader>
        <CardContent className="px-5 pb-4 pt-4">
          {loading
            ? <Skeleton className="h-[240px] w-full" />
            : heatmapRows.length === 0
              ? <p className="py-8 text-center text-sm text-muted-foreground">
                  No submitted reports in this period yet.
                </p>
              : <Heatmap rows={heatmapRows} weekLabels={heatWeeks} />
          }
        </CardContent>
      </Card>
    </>
  );
}
