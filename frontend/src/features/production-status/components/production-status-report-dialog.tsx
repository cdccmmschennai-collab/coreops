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
  REPORT_EMPTY_TITLE,
  REPORT_ERROR_TITLE,
  REPORT_NOTHING_TO_DOWNLOAD,
  REPORT_TITLE,
  reportErrorMessage,
  reportSubtitle,
  type ProductionStatusReportTableRow,
} from "../production-status-report";
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
  // Not fetched until the PM actually opens the dialog - the projects list must
  // not pay for a report nobody asked for.
  const query = useProductionStatusReport(open);
  const [downloading, setDownloading] = React.useState(false);

  const rows: ProductionStatusReportTableRow[] = React.useMemo(
    () => buildProductionStatusReportRows(query.data?.rows),
    [query.data],
  );

  const canDownload = canDownloadReport(query.data?.rows, query.isFetching);

  async function onDownload() {
    setDownloading(true);
    try {
      await downloadProductionStatusReportXlsx();
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
          <p className="text-sm text-muted-foreground">
            {query.data ? reportSubtitle(query.data.row_count) : REPORT_ALL_PROJECTS}
          </p>
        </DialogHeader>

        {/* Download on the left of Close, both above the table so they stay
            reachable without scrolling a long report to the bottom. */}
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Button
            onClick={() => void onDownload()}
            disabled={!canDownload || downloading}
            loading={downloading}
            title={canDownload ? undefined : REPORT_NOTHING_TO_DOWNLOAD}
          >
            <Download className="h-4 w-4" />
            Download Excel
          </Button>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Close
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

        {!query.isFetching && !query.isError && rows.length === 0 && (
          <EmptyState
            icon={ClipboardList}
            title={REPORT_EMPTY_TITLE}
            description={REPORT_EMPTY_HINT}
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
