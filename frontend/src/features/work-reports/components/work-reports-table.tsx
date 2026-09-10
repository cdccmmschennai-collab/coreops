"use client";

import { useRouter } from "next/navigation";

import { Pagination } from "@/components/data/pagination";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

import { AutoBadge, StatusBadge } from "./status-badge";
import { projectSummary } from "../project-summary";
import type { WorkReport, WorkReportPage } from "../types";

interface WorkReportsTableProps {
  data: WorkReportPage | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  onPageChange: (offset: number) => void;
  showEmployee: boolean;
  emptyAction?: React.ReactNode;
}

export function WorkReportsTable({
  data,
  isLoading,
  isError,
  onRetry,
  onPageChange,
  showEmployee,
  emptyAction,
}: WorkReportsTableProps) {
  const router = useRouter();
  const cols = showEmployee ? 4 : 3;
  const rows = data?.items ?? [];
  const showRows = !isLoading && !isError && rows.length > 0;
  const showEmpty = !isLoading && !isError && rows.length === 0;

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      {/* `overflow-anchor: none` excludes the table (and its rows) from being
          picked as the browser's scroll anchor, which leaves the pagination bar
          below it as the anchor instead.

          Pages are not the same height — the last page is short (12 rows vs 20),
          and even two full pages differ because a long project name wraps. When
          the offset changes the whole row set is replaced, so any anchor the
          browser had chosen inside the table is destroyed and no scroll
          adjustment happens. Going to a SHORTER page that is invisible: the
          browser clamps scroll to the new maximum and you stay at the bottom.
          Going to a TALLER page nothing clamps, so the page grows underneath a
          stationary viewport and the pagination controls drop below the fold —
          which is why Prev felt broken while Next did not.

          The pagination bar is never unmounted (`showRows` stays true across a
          page change thanks to the list query's placeholderData), so it is a
          stable anchor: the browser now keeps it visually fixed and absorbs the
          height change above it in both directions. */}
      <Table className="[overflow-anchor:none]">
        <TableHeader>
          <TableRow>
            <TableHead className="w-32">Date</TableHead>
            {showEmployee && <TableHead className="w-48">Employee</TableHead>}
            <TableHead>Projects</TableHead>
            <TableHead className="w-32">Status</TableHead>
          </TableRow>
        </TableHeader>

        {isLoading && <TableSkeleton cols={cols} />}

        {showRows && (
          <TableBody>
            {rows.map((r: WorkReport) => {
              const proj = projectSummary(r);
              return (
                <TableRow
                  key={r.id}
                  className="cursor-pointer"
                  onClick={() => router.push(`/work-reports/${r.id}`)}
                >
                  <TableCell className="font-medium tabular">{r.report_date}</TableCell>
                  {showEmployee && (
                    <TableCell className="text-muted-foreground">
                      {r.employee_name ?? "—"}
                    </TableCell>
                  )}
                  <TableCell className="text-sm font-medium text-foreground" title={proj.title}>
                    {proj.label}
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-1.5">
                      <StatusBadge status={r.status} editRequested={!!r.edit_requested_at} />
                      <AutoBadge origin={r.origin} />
                      {r.report_mode === "split_day" && (
                        <Badge variant="neutral">Split</Badge>
                      )}
                    </span>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        )}
      </Table>

      {isError && <ErrorState message="Could not load work reports." onRetry={onRetry} />}
      {showEmpty && (
        <EmptyState
          title="No work reports"
          description="No reports match the current filters."
          action={emptyAction}
        />
      )}
      {showRows && data && (
        <Pagination
          total={data.total}
          limit={data.limit}
          offset={data.offset}
          onPageChange={onPageChange}
        />
      )}
    </div>
  );
}
