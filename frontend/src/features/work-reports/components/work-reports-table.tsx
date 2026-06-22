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
import { StatusBadge } from "./status-badge";
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
      <Table>
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
                    <StatusBadge status={r.status} />
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
