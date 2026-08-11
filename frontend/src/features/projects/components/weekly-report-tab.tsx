"use client";

import * as React from "react";
import { CalendarRange, Download, Lock } from "lucide-react";
import { toast } from "sonner";

import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { AppError } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { useUrlState } from "@/lib/use-url-state";

import { downloadWeeklyReportXlsx } from "../api";
import { useProjectWeeklyReport } from "../hooks";
import {
  WEEKLY_REPORT_COLUMNS,
  WEEKLY_REPORT_CYCLES,
  WEEKLY_REPORT_CYCLE_PARAM,
  WEEKLY_REPORT_DEFAULT_CYCLE,
  WEEKLY_REPORT_DOWNLOAD_ERROR,
  WEEKLY_REPORT_EMPTY_HINT,
  WEEKLY_REPORT_EMPTY_TITLE,
  WEEKLY_REPORT_ERROR_HINT,
  WEEKLY_REPORT_ERROR_TITLE,
  WEEKLY_REPORT_FORBIDDEN_HINT,
  WEEKLY_REPORT_FORBIDDEN_TITLE,
  buildWeeklyReportRows,
  canDownloadWeeklyReport,
  formatCycleRange,
  resolveWeeklyReportCycle,
  type WeeklyReportTableRow,
} from "../weekly-report";

/**
 * Project Weekly Report - every activity line reported on this project during
 * one Friday-Thursday cycle, for the assigned Head.
 *
 * Two things this tab is deliberately not:
 *
 *   It is not the Summary. Summary is the compact tag-scope progress table for
 *   every project viewer; this is the detailed operational record, restricted
 *   to the Head, and it carries doc/BOM/spares/pages/records work, task-mode
 *   work and non-benchmark work alongside tag work.
 *
 *   It is not a report builder. The only control is Previous / Current Week -
 *   no employee filter, no activity filter, no date picker. The complete
 *   downloadable record is the Excel file.
 *
 * The table and the .xlsx come from the SAME backend dataset (the preview
 * endpoint and the export endpoint call one service), and this component does
 * no filtering, sorting or arithmetic of its own - see ../weekly-report.ts,
 * where every formatting rule lives so `node --test` can cover it.
 */
export function WeeklyReportTab({
  projectId,
  projectCode,
}: {
  projectId: string;
  /** From the project row the page already loaded, so the heading names the
   *  project before the report resolves. Code only - never the name. */
  projectCode: string;
}) {
  // The selected cycle lives in the URL alongside ?tab=weekly-report, so
  // navigating away and back returns to the same week.
  const [cycleParam, setCycleParam] = useUrlState(
    WEEKLY_REPORT_CYCLE_PARAM,
    WEEKLY_REPORT_DEFAULT_CYCLE,
  );
  const cycle = resolveWeeklyReportCycle(cycleParam);
  const [downloading, setDownloading] = React.useState(false);

  const query = useProjectWeeklyReport(projectId, cycle);
  const rows: WeeklyReportTableRow[] = React.useMemo(
    () => buildWeeklyReportRows(query.data?.rows),
    [query.data],
  );

  const period = query.data?.period;
  const range = formatCycleRange(period?.start_date, period?.end_date);
  const canDownload = canDownloadWeeklyReport(query.data?.rows, query.isFetching);

  async function onDownload() {
    setDownloading(true);
    try {
      // The SELECTED cycle, explicitly: downloading while Previous Week is on
      // screen must never hand back the current week.
      await downloadWeeklyReportXlsx(projectId, cycle);
    } catch {
      toast.error(WEEKLY_REPORT_DOWNLOAD_ERROR);
    } finally {
      setDownloading(false);
    }
  }

  const forbidden = query.error instanceof AppError && query.error.status === 403;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Weekly Report</CardTitle>
      </CardHeader>
      <CardContent className="px-0 pb-0">
        <div className="flex flex-wrap items-end justify-between gap-4 px-6 pb-4">
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Project: <span className="font-mono text-foreground">{projectCode}</span>
            </p>

            {/* Segmented cycle selector. Switching loads immediately - there is
                nothing to save, so there is no Save button. */}
            <div
              className="inline-flex rounded-md border border-border p-0.5"
              role="group"
              aria-label="Report week"
            >
              {WEEKLY_REPORT_CYCLES.map((option) => {
                const active = option.value === cycle;
                return (
                  <button
                    key={option.value}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setCycleParam(option.value)}
                    className={cn(
                      "rounded px-3 py-1.5 text-sm font-medium transition-colors",
                      active
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>

            {/* The resolved dates, always visible: the Head should never have to
                guess which days "Current Week" covers. */}
            <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <CalendarRange className="h-4 w-4" aria-hidden />
              {query.isFetching ? "Loading week..." : range}
            </p>
          </div>

          <Button
            variant="secondary"
            onClick={() => void onDownload()}
            disabled={!canDownload || downloading}
            loading={downloading}
            title={
              canDownload
                ? undefined
                : "There is nothing to download for this week."
            }
          >
            <Download className="h-4 w-4" />
            Download Excel
          </Button>
        </div>

        {query.isFetching ? (
          // A fresh skeleton on every cycle change, never last week's rows
          // sitting under this week's heading.
          <div className="px-6 pb-6">
            <Skeleton className="h-64" />
          </div>
        ) : query.isError || !query.data ? (
          <div className="px-6 pb-6">
            {forbidden ? (
              <EmptyState
                icon={Lock}
                title={WEEKLY_REPORT_FORBIDDEN_TITLE}
                description={WEEKLY_REPORT_FORBIDDEN_HINT}
              />
            ) : (
              <ErrorState
                title={WEEKLY_REPORT_ERROR_TITLE}
                message={WEEKLY_REPORT_ERROR_HINT}
                onRetry={() => void query.refetch()}
              />
            )}
          </div>
        ) : rows.length === 0 ? (
          // Never an empty grid under a header row - that reads as a broken
          // page rather than as "nothing was reported".
          <EmptyState
            icon={CalendarRange}
            title={WEEKLY_REPORT_EMPTY_TITLE}
            description={WEEKLY_REPORT_EMPTY_HINT}
          />
        ) : (
          <>
            <p className="px-6 pb-3 text-sm text-muted-foreground">
              {rows.length} {rows.length === 1 ? "entry" : "entries"} reported.
            </p>
            {/*
              Fifteen columns cannot be squeezed into a project page without
              becoming unreadable. `Table` already supplies the overflow-x-auto
              wrapper; the min-width lives on the <table> so the overflow becomes
              a visible scrollbar instead of crushed columns, and the wide free-
              text columns wrap rather than clip. The header sticks so a long
              week stays readable while scrolling.
            */}
            <Table className="min-w-[80rem]">
              <TableHeader className="sticky top-0 z-10 bg-card">
                <TableRow>
                  {WEEKLY_REPORT_COLUMNS.map((col) => (
                    <TableHead
                      key={col.key}
                      className={cn(
                        "whitespace-nowrap",
                        col.numeric && "text-right",
                        col.key === "remarks" && "min-w-[22rem]",
                        col.key === "subActivity" && "min-w-[18rem]",
                        col.key === "activity" && "min-w-[10rem]",
                      )}
                    >
                      {col.label}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.key}>
                    {WEEKLY_REPORT_COLUMNS.map((col) => (
                      <TableCell
                        key={col.key}
                        className={cn(
                          "align-top",
                          col.numeric
                            ? "whitespace-nowrap text-right tabular"
                            : col.wrap
                              ? "break-words"
                              : "whitespace-nowrap",
                          col.key === "project" && "font-mono",
                          col.key === "remarks" && "text-muted-foreground",
                        )}
                      >
                        {row[col.key as keyof WeeklyReportTableRow]}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}
      </CardContent>
    </Card>
  );
}
