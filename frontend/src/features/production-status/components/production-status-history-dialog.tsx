"use client";

import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
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
import { formatDateTime } from "@/lib/format";

import { useProductionStatusHistory } from "../hooks";
import {
  buildProductionStatusRows,
  NO_HISTORY_HINT,
  NO_HISTORY_TITLE,
  productionStatusErrorMessage,
} from "../production-status";
import { ProductionStatusBadge } from "./status-badge";

export interface HistoryTarget {
  activityId: string;
  activityLabel: string;
  revision: string;
}

/**
 * Every update ever recorded for ONE revision + activity, newest first.
 *
 * Reads the Phase 1 history endpoint with both filters applied, so REV-0 and
 * REV-1 of the same activity open as two separate trails — changing revision
 * never rewrites or hides the other one. Nothing here is derived: the rows are
 * the stored records, in the order the API returned them.
 */
export function ProductionStatusHistoryDialog({
  projectId,
  target,
  onOpenChange,
}: {
  projectId: string;
  /** Null closes the dialog; a target opens it and drives the query. */
  target: HistoryTarget | null;
  onOpenChange: (open: boolean) => void;
}) {
  const open = target !== null;
  const query = useProductionStatusHistory(
    projectId,
    { activityId: target?.activityId, revision: target?.revision },
    open,
  );
  const rows = buildProductionStatusRows(query.data, formatDateTime);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>
            {target ? `${target.revision} · ${target.activityLabel}` : "History"}
          </DialogTitle>
        </DialogHeader>

        {query.isLoading && <Skeleton className="h-40" />}

        {!query.isLoading && query.isError && (
          <ErrorState
            title="Couldn't load history"
            message={productionStatusErrorMessage(
              query.error instanceof AppError ? query.error.status : null,
              query.error instanceof AppError ? query.error.message : null,
            )}
            onRetry={() => void query.refetch()}
          />
        )}

        {!query.isLoading && !query.isError && rows.length === 0 && (
          <EmptyState title={NO_HISTORY_TITLE} description={NO_HISTORY_HINT} />
        )}

        {!query.isLoading && !query.isError && rows.length > 0 && (
          <div className="max-h-[60vh] overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">TAG</TableHead>
                  <TableHead className="text-right">DOC</TableHead>
                  <TableHead className="text-right">SPARES</TableHead>
                  <TableHead className="text-right">CRS</TableHead>
                  <TableHead>Completed On</TableHead>
                  <TableHead>Remarks</TableHead>
                  <TableHead>By</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.key}>
                    <TableCell>
                      <ProductionStatusBadge status={r.statusValue ?? r.status} />
                    </TableCell>
                    <TableCell className="text-right tabular">{r.tag}</TableCell>
                    <TableCell className="text-right tabular">{r.doc}</TableCell>
                    <TableCell className="text-right tabular">{r.spares}</TableCell>
                    <TableCell className="text-right tabular">{r.crs}</TableCell>
                    <TableCell className="whitespace-nowrap">{r.completedOn}</TableCell>
                    {/* Line breaks are preserved - a remark is what the author
                        typed, not a single squashed line. */}
                    <TableCell className="max-w-xs whitespace-pre-wrap">
                      {r.remarks ?? "-"}
                    </TableCell>
                    <TableCell className="whitespace-nowrap">{r.by}</TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {r.updated}
                    </TableCell>
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
