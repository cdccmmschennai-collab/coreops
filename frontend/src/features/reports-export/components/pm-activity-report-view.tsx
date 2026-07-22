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
import { useUrlState } from "@/lib/use-url-state";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { useProjectOptions } from "@/features/work-reports/project-options";

import { downloadActivityXlsx } from "../api";
import { COUNT_COLUMNS, sumCount } from "../columns";
import { remarkLines } from "../remarks";
import { useActivityOptions, useActivityRows, useSubActivityOptions } from "../hooks";
import { type ActivityReportFilters } from "../types";

const ALL = "all";

const TH = "whitespace-nowrap px-3 py-2 text-left text-xs font-medium text-muted-foreground";
const TD = "px-3 py-2.5 align-top text-sm";

export function PmActivityReportView() {
  // Filters live in the URL so they survive navigating away and back.
  const [employeeId, setEmployeeId] = useUrlState("employee_id", "");
  const [projectId, setProjectId] = useUrlState("project_id", "");
  const [activityId, setActivityId] = useUrlState("activity_id", "");
  const [subActivityId, setSubActivityId] = useUrlState("sub_activity_id", "");
  const [fromDate, setFromDate] = useUrlState("from", "");
  const [toDate, setToDate] = useUrlState("to", "");
  const filters: ActivityReportFilters = {
    employee_id: employeeId,
    project_id: projectId,
    activity_id: activityId,
    sub_activity_id: subActivityId,
    from: fromDate,
    to: toDate,
  };
  const [exporting, setExporting] = React.useState(false);

  const { items: employees } = useEmployeeOptions();
  const { items: projects } = useProjectOptions();
  const activities = useActivityOptions();
  const subActivities = useSubActivityOptions();

  const { data, isLoading, isFetching } = useActivityRows(filters);
  const rows = data?.rows ?? [];
  const totalActivities = rows.reduce((s, row) => s + row.activities.length, 0);
  // Leave-type days are day-status-only rows (zero activities) but must still
  // show and export — so gate on the row count, not the activity count.
  const hasRows = rows.length > 0;

  const subOptions = (subActivities.data ?? []).filter(
    (s) => !filters.activity_id || s.activity_id === filters.activity_id,
  );

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
    <Button onClick={onExport} disabled={exporting || !hasRows}>
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
        <Select value={filters.employee_id || ALL} onValueChange={(v) => setEmployeeId(v === ALL ? "" : v)}>
          <SelectTrigger className="sm:w-56"><SelectValue placeholder="Employee" /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All employees</SelectItem>
            {employees.map((e) => (
              <SelectItem key={e.id} value={e.id}>{e.full_name} · {e.employee_code}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={filters.project_id || ALL} onValueChange={(v) => setProjectId(v === ALL ? "" : v)}>
          <SelectTrigger className="sm:w-56"><SelectValue placeholder="Project Code" /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All projects</SelectItem>
            {projects.map((p) => (
              <SelectItem key={p.id} value={p.id}>{p.code} · {p.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={filters.activity_id || ALL} onValueChange={(v) => { setActivityId(v === ALL ? "" : v); setSubActivityId(""); }}>
          <SelectTrigger className="sm:w-48"><SelectValue placeholder="Activity" /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All activities</SelectItem>
            {(activities.data ?? []).map((a) => (
              <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={filters.sub_activity_id || ALL} onValueChange={(v) => setSubActivityId(v === ALL ? "" : v)}>
          <SelectTrigger className="sm:w-56"><SelectValue placeholder="Sub Activity" /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All sub activities</SelectItem>
            {subOptions.map((s) => (
              <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="flex items-center gap-1">
          <Input type="date" className="sm:w-40" value={filters.from} onChange={(e) => setFromDate(e.target.value)} aria-label="From date" />
          <span className="text-muted-foreground">→</span>
          <Input type="date" className="sm:w-40" value={filters.to} onChange={(e) => setToDate(e.target.value)} aria-label="To date" />
        </div>
      </div>

      {/* Preview — readable activity list (one row per Employee+Date, activities
          stacked in a single cell). The dynamic spreadsheet columns live only in
          the Excel export. */}
      {isLoading ? (
        <Skeleton className="h-[420px] w-full" />
      ) : !hasRows ? (
        <div className="rounded-lg border border-border px-3 py-16 text-center text-sm text-muted-foreground">
          No records match the current filters.
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
                {COUNT_COLUMNS.map((c) => (
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
                  {COUNT_COLUMNS.map((c) => {
                    const total = sumCount(row.activities, c.key);
                    return (
                      <td key={c.key} className={cn(TD, "tabular text-right", total === 0 && "text-muted-foreground/50")}>
                        {total}
                      </td>
                    );
                  })}
                  <td className={cn(TD, "min-w-[16rem] whitespace-pre-line text-muted-foreground")}>
                    {remarkLines(row.remarks).map((line, li) => (
                      <span key={li} className="block">{line}</span>
                    ))}
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
