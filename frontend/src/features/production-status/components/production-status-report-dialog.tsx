"use client";

import * as React from "react";
import { ClipboardList, Download } from "lucide-react";
import { toast } from "sonner";

import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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

import { downloadProductionStatusReportXlsx } from "../api";
import { useProductionStatusReport } from "../hooks";
import {
  buildProductionStatusReportRows,
  canDownloadReport,
  REPORT_ALL_PROJECTS,
  REPORT_BLANK,
  REPORT_COLUMNS,
  REPORT_DOWNLOAD_ERROR,
  REPORT_EMPTY_HINT,
  REPORT_EMPTY_MONTH_HINT,
  REPORT_EMPTY_MONTH_TITLE,
  REPORT_EMPTY_TITLE,
  REPORT_ERROR_TITLE,
  REPORT_MONTH_ALL,
  REPORT_NOTHING_TO_DOWNLOAD,
  REPORT_TITLE,
  reportErrorMessage,
  reportMonthParam,
  reportSubtitle,
  type ProductionStatusReportTableRow,
} from "../production-status-report";
import { ReportMonthSelect } from "./report-month-select";
import { ProductionStatusBadge } from "./status-badge";

/**
 * The PM's cumulative Production Status preview.
 *
 * One screen, one dataset: the latest recorded status of every project +
 * revision + activity, so the PM reviews the whole picture before downloading
 * it instead of opening each project's tab in turn.
 *
 * The table and the .xlsx come from the SAME backend call (the preview endpoint
 * and the export endpoint both run `cumulative_report`), and this component
 * does no filtering, sorting, numbering or arithmetic of its own - every
 * formatting rule lives in ../production-status-report.ts, where `node --test`
 * can cover it.
 *
 * The Month dropdown does not change that. It is a query parameter, not a pass
 * over rows: choosing August refetches the report FOR August, and the Download
 * button sends the very same parameter, so the file is exactly the rows on
 * screen for whatever month is chosen. Nothing is filtered in the browser, and
 * no large historical dataset is fetched to be sifted here.
 *
 * The month is the record's created_at month - an IN PROGRESS record has no
 * completion date, so filtering on `completed_on` would hide exactly the rows a
 * PM opens a month to look at. It is also the only filter: the report stays
 * all-project and cumulative.
 *
 * Read-only by construction. There is no form here, nothing is saved, and the
 * append-only history behind each row is untouched - the full trail is still
 * read only through each project's own History dialog.
 */
export function ProductionStatusReportDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  // The chosen month, "all" until the PM picks one. Local state, not a URL
  // filter: this is a dialog, and the choice lasts as long as it is open.
  const [month, setMonth] = React.useState<string>(REPORT_MONTH_ALL);
  // The value actually sent to the API: undefined for All Months. One
  // conversion, shared by the preview query and the download below, so the two
  // cannot ask for different months.
  const monthParam = reportMonthParam(month);

  // Not fetched until the PM actually opens the dialog - the projects list must
  // not pay for a report nobody asked for. The month is part of the request, so
  // the FILTERING is the backend's: the browser never receives every historical
  // record to sift through.
  const query = useProductionStatusReport(open, monthParam);
  const [downloading, setDownloading] = React.useState(false);

  const rows: ProductionStatusReportTableRow[] = React.useMemo(
    () => buildProductionStatusReportRows(query.data?.rows),
    [query.data],
  );

  const canDownload = canDownloadReport(query.data?.rows, query.isFetching);

  async function onDownload() {
    setDownloading(true);
    try {
      // The SAME month the preview was fetched with, through the same helper.
      // Nothing is filtered client-side, so the file is exactly these rows.
      await downloadProductionStatusReportXlsx(monthParam);
    } catch {
      toast.error(REPORT_DOWNLOAD_ERROR);
    } finally {
      setDownloading(false);
    }
  }

  const status = query.error instanceof AppError ? query.error.status : null;
  const message = query.error instanceof AppError ? query.error.message : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[95vw] sm:max-w-6xl">
        <DialogHeader>
          <DialogTitle>{REPORT_TITLE}</DialogTitle>
          {/* Both halves come from the SAME payload - `row_count` and the
              backend's echo of the month it filtered on - so the count and the
              month it claims to describe can never be a step out of sync while
              a switch is in flight. */}
          <p className="text-sm text-muted-foreground">
            {query.data
              ? reportSubtitle(query.data.row_count, query.data.month)
              : REPORT_ALL_PROJECTS}
          </p>
        </DialogHeader>

        {/* Month on the left, download on the right of it, both above the table
            so they stay reachable without scrolling a long report to the
            bottom. There is no Close button: the dialog's own X closes it, the
            way every other dialog in CoreOps is dismissed. */}
        <div className="mb-4 flex flex-wrap items-end gap-3">
          {/* The months come with the report payload - no second request, and
              no range invented here. A failed report has none to offer, so the
              picker would only be a dead control next to the error. */}
          <ReportMonthSelect
            value={month}
            onChange={setMonth}
            months={query.data?.months}
            disabled={query.isError}
          />
          <Button
            onClick={() => void onDownload()}
            disabled={!canDownload || downloading}
            loading={downloading}
            title={canDownload ? undefined : REPORT_NOTHING_TO_DOWNLOAD}
          >
            <Download className="h-4 w-4" />
            Download Excel
          </Button>
        </div>

        {query.isFetching && <Skeleton className="h-72" />}

        {!query.isFetching && query.isError && (
          <ErrorState
            title={REPORT_ERROR_TITLE}
            message={reportErrorMessage(status, message)}
            // A 403 will not resolve by retrying; anything else might.
            onRetry={status === 403 ? undefined : () => void query.refetch()}
          />
        )}

        {/* A month with nothing in it reads differently from a system with
            nothing in it - otherwise a PM who picked the wrong month is told
            production status has never been recorded. Both are normal, and
            neither is an error. Which one applies is decided by the month the
            RESPONSE was filtered on, not by the dropdown. */}
        {!query.isFetching && !query.isError && rows.length === 0 && (
          <EmptyState
            icon={ClipboardList}
            title={query.data?.month ? REPORT_EMPTY_MONTH_TITLE : REPORT_EMPTY_TITLE}
            description={
              query.data?.month ? REPORT_EMPTY_MONTH_HINT : REPORT_EMPTY_HINT
            }
          />
        )}

        {!query.isFetching && !query.isError && rows.length > 0 && (
          // Twelve columns cannot be squeezed into a dialog without becoming
          // unreadable. This wrapper scrolls in BOTH directions - horizontally
          // so the columns keep their width instead of being crushed, and
          // vertically so a long report stays inside the dialog. The min-width
          // on the table is what turns the overflow into a real scrollbar.
          <div className="max-h-[60vh] overflow-auto">
            <Table className="min-w-[72rem]">
              <TableHeader className="sticky top-0 z-10 bg-card">
                <TableRow>
                  {REPORT_COLUMNS.map((col) => (
                    <TableHead
                      key={col.key}
                      className={cn(
                        "whitespace-nowrap",
                        col.numeric && "text-right",
                        // Remarks gets real room; everything else stays compact.
                        col.key === "remarks" && "min-w-[20rem]",
                        col.key === "activity" && "min-w-[12rem]",
                        // Now carries project + plant + revision in one cell.
                        col.key === "projectPlant" && "min-w-[16rem]",
                      )}
                    >
                      {col.label}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.key}>
                    <TableCell className="text-right tabular align-top">
                      {r.serial}
                    </TableCell>
                    {/* Project, Maintenance Plant and revision in one cell -
                        exactly the string the Excel's PROJECT / PLANT column
                        carries, because both read the same backend field. */}
                    <TableCell className="whitespace-nowrap font-mono align-top">
                      {r.projectPlant}
                    </TableCell>
                    <TableCell className="align-top">{r.activity}</TableCell>
                    <TableCell className="align-top">
                      <ProductionStatusBadge status={r.statusValue} />
                    </TableCell>
                    {/* Four independent counts. A zero shows as 0, exactly as
                        the Excel cell carries it - never as a placeholder. */}
                    <TableCell className="text-right tabular align-top">{r.tag}</TableCell>
                    <TableCell className="text-right tabular align-top">{r.doc}</TableCell>
                    <TableCell className="text-right tabular align-top">{r.spares}</TableCell>
                    <TableCell className="text-right tabular align-top">{r.crs}</TableCell>
                    {/* Blank when the update has not completed. */}
                    <TableCell className="whitespace-nowrap align-top">
                      {r.completedOn}
                    </TableCell>
                    {/* Constrained and wrapped for the layout's sake, but the
                        text itself is complete - line breaks preserved, nothing
                        truncated, and the Excel carries the same full string. */}
                    <TableCell className="max-w-sm whitespace-pre-wrap break-words align-top text-muted-foreground">
                      {r.remarks ?? REPORT_BLANK}
                    </TableCell>
                    {/* The real person, straight from the API's `by` field. */}
                    <TableCell className="whitespace-nowrap align-top">{r.by}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
