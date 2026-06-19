"use client";

import * as React from "react";
import { Download } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { useProjectOptions } from "@/features/work-reports/project-options";

import { downloadActivityXlsx } from "../api";
import { useActivityOptions, useActivityRows, useSubActivityOptions } from "../hooks";
import {
  EMPTY_FILTERS,
  type ActivityCell,
  type ActivityReportFilters,
} from "../types";

const ALL = "all";

// Daily count columns — summed across the day's activities (the per-activity
// breakdown lives only in the Excel export's dynamic columns).
const COUNTS = [
  { label: "Tags", key: "tags" },
  { label: "Docs", key: "docs" },
  { label: "BOM", key: "bom" },
  { label: "Spares", key: "spares" },
] as const;

const TH = "whitespace-nowrap px-3 py-2 text-left text-xs font-medium text-muted-foreground";
const TD = "px-3 py-2.5 align-top text-sm";

function sumKey(acts: ActivityCell[], key: (typeof COUNTS)[number]["key"]) {
  return acts.reduce((s, a) => s + (a[key] ?? 0), 0);
}

export function PmActivityReportView() {
  const [filters, setFilters] = React.useState<ActivityReportFilters>(EMPTY_FILTERS);
  const [exporting, setExporting] = React.useState(false);

  const { items: employees } = useEmployeeOptions();
  const { items: projects } = useProjectOptions();
  const activities = useActivityOptions();
  const subActivities = useSubActivityOptions();

  const { data, isLoading, isFetching } = useActivityRows(filters);
  const rows = data?.rows ?? [];
  const totalActivities = rows.reduce((s, row) => s + row.activities.length, 0);

  const subOptions = (subActivities.data ?? []).filter(
    (s) => !filters.activity_id || s.activity_id === filters.activity_id,
  );

  function patch(p: Partial<ActivityReportFilters>) {
    setFilters((f) => ({ ...f, ...p }));
  }

  async function onExport() {
    setExporting(true);
    try {
      await downloadActivityXlsx(filters);
    } catch {
      toast.error("Export failed. Please try again.");
    } finally {
      setExporting(false);
    }
  }

  const exportButton = (
    <Button onClick={onExport} disabled={exporting || totalActivities === 0}>
      <Download className="h-4 w-4" />
      {exporting ? "Exporting…" : "Export Excel"}
    </Button>
  );

  return (
    <>
      <PageHeader
        title="Reports"
        subtitle={`Weekly Activity Report · ${totalActivities} ${totalActivities === 1 ? "activity" : "activities"}`}
        actions={exportButton}
      />

      {/* Filters */}
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <Select value={filters.employee_id || ALL} onValueChange={(v) => patch({ employee_id: v === ALL ? "" : v })}>
          <SelectTrigger className="sm:w-56"><SelectValue placeholder="Employee" /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All employees</SelectItem>
            {employees.map((e) => (
              <SelectItem key={e.id} value={e.id}>{e.full_name} · {e.employee_code}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={filters.project_id || ALL} onValueChange={(v) => patch({ project_id: v === ALL ? "" : v })}>
          <SelectTrigger className="sm:w-56"><SelectValue placeholder="Project Code" /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All projects</SelectItem>
            {projects.map((p) => (
              <SelectItem key={p.id} value={p.id}>{p.code} · {p.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={filters.activity_id || ALL} onValueChange={(v) => patch({ activity_id: v === ALL ? "" : v, sub_activity_id: "" })}>
          <SelectTrigger className="sm:w-48"><SelectValue placeholder="Activity" /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All activities</SelectItem>
            {(activities.data ?? []).map((a) => (
              <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={filters.sub_activity_id || ALL} onValueChange={(v) => patch({ sub_activity_id: v === ALL ? "" : v })}>
          <SelectTrigger className="sm:w-56"><SelectValue placeholder="Sub Activity" /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All sub activities</SelectItem>
            {subOptions.map((s) => (
              <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="flex items-center gap-1">
          <Input type="date" className="sm:w-40" value={filters.from} onChange={(e) => patch({ from: e.target.value })} aria-label="From date" />
          <span className="text-muted-foreground">→</span>
          <Input type="date" className="sm:w-40" value={filters.to} onChange={(e) => patch({ to: e.target.value })} aria-label="To date" />
        </div>
      </div>

      {/* Preview — readable activity list (one row per Employee+Date, activities
          stacked in a single cell). The dynamic spreadsheet columns live only in
          the Excel export. */}
      {isLoading ? (
        <Skeleton className="h-[420px] w-full" />
      ) : totalActivities === 0 ? (
        <div className="rounded-lg border border-border px-3 py-16 text-center text-sm text-muted-foreground">
          No activity records match the current filters.
        </div>
      ) : (
        <div className="relative max-h-[65vh] overflow-auto rounded-lg border border-border">
          <table className="w-full border-collapse">
            <thead className="sticky top-0 z-10 bg-secondary/60 backdrop-blur">
              <tr className="border-b border-border">
                <th className={TH}>Date</th>
                <th className={TH}>Employee</th>
                <th className={cn(TH, "text-center")}>Activities</th>
                <th className={TH}>Activity Summary</th>
                {COUNTS.map((c) => (
                  <th key={c.key} className={cn(TH, "text-right")}>{c.label}</th>
                ))}
                <th className={TH}>Remarks</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={ri} className="border-b border-border last:border-0 hover:bg-secondary/30">
                  <td className={cn(TD, "tabular whitespace-nowrap text-muted-foreground")}>
                    {row.report_date}
                    {row.day_status ? (
                      <span className="mt-0.5 block text-xs text-muted-foreground/70">{row.day_status}</span>
                    ) : null}
                  </td>
                  <td className={cn(TD, "whitespace-nowrap font-medium")}>{row.employee_label}</td>
                  <td className={cn(TD, "text-center")}>
                    <span className="inline-flex min-w-[1.5rem] items-center justify-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">
                      {row.activities.length}
                    </span>
                  </td>
                  <td className={cn(TD, "min-w-[18rem]")}>
                    <ul className="space-y-1.5">
                      {row.activities.map((a, ai) => (
                        <li key={ai} className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
                          <span className="rounded bg-secondary px-1.5 py-0.5 text-xs font-medium tabular">
                            {a.project_code ?? "—"}
                          </span>
                          <span className="font-medium">{a.activity_type ?? "—"}</span>
                          {a.sub_activity_type ? (
                            <span className="text-xs text-muted-foreground">· {a.sub_activity_type}</span>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  </td>
                  {COUNTS.map((c) => {
                    const total = sumKey(row.activities, c.key);
                    return (
                      <td key={c.key} className={cn(TD, "tabular text-right", total === 0 && "text-muted-foreground/50")}>
                        {total}
                      </td>
                    );
                  })}
                  <td className={cn(TD, "min-w-[16rem] whitespace-pre-wrap text-muted-foreground")}>
                    {row.remarks ?? ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {isFetching && (
            <div className="pointer-events-none absolute right-2 top-2 text-[10px] text-muted-foreground">updating…</div>
          )}
        </div>
      )}
    </>
  );
}
