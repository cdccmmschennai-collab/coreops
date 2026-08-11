"use client";

import * as React from "react";
import { CalendarRange, Download, Lock } from "lucide-react";
import { toast } from "sonner";

import { CycleSelect } from "@/components/data/cycle-select";
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
  WEEKLY_REPORT_CYCLE_LABEL,
  WEEKLY_REPORT_CYCLE_PARAM,
  WEEKLY_REPORT_DEFAULT_CYCLE,
  WEEKLY_REPORT_DOWNLOAD_ERROR,
  WEEKLY_REPORT_EMPTY_HINT,
  WEEKLY_REPORT_EMPTY_TITLE,
  WEEKLY_REPORT_ERROR_HINT,
  WEEKLY_REPORT_ERROR_TITLE,
  WEEKLY_REPORT_FORBIDDEN_HINT,
  WEEKLY_REPORT_FORBIDDEN_TITLE,
  WEEKLY_REPORT_WEEK_OFFSETS,
  buildWeeklyReportRows,
  canDownloadWeeklyReport,
  resolveWeeklyReportCycle,
  weeklyReportCycleForOffset,
  weeklyReportWeekOffset,
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
 *   It is not a report builder. The only control is the Current / Previous week
 *   cycle selector - no employee filter, no activity filter, no date picker. The
 *   complete downloadable record is the Excel file.
 *
 * The table and the .xlsx come from the SAME backend dataset (the preview
 * endpoint and the export endpoint call one service), and this component does
 * no filtering, sorting or arithmetic of its own - see ../weekly-report.ts,
 * where every formatting rule lives so `node --test` can cover it.
 */
export function WeeklyReportTab({ projectId }: { projectId: string }) {
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
        {/* One controls row: cycle on the left, download on the right. The
            project code is NOT repeated here - the page header two rows up
            already names the project this tab belongs to. `flex-wrap` is what
            makes the download drop below the selector on a narrow screen, so
            nothing is positioned absolutely. */}
        <div className="flex flex-wrap items-center justify-between gap-3 px-6 pb-4">
          {/* The same control Employee Performance uses, so a week picker looks
              and behaves identically wherever it appears. Switching loads
              immediately - there is nothing to save, so there is no Save
              button. The dates live inside it; there is no second date line. */}
          <CycleSelect
            value={weeklyReportWeekOffset(cycle)}
            options={WEEKLY_REPORT_WEEK_OFFSETS}
            labels={WEEKLY_REPORT_CYCLE_LABEL}
            onChange={(offset) => setCycleParam(weeklyReportCycleForOffset(offset))}
            ariaLabel="Select report week"
          />

          {/* Default (primary) variant and "Export Excel" wording, matching
              every other export button in CoreOps - Employee Performance's
              "Export Full Cycle Report" and the Reports module. An export is
              the same action wherever it appears, so it looks the same. */}
          <Button
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
            Export Excel
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
