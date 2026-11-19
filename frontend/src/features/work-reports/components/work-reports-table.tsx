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
import { markReportOpenedFromList } from "../return-nav";
import { reportReworkState } from "../rework-approval";

const REWORK_MARKER: Record<
  "pending" | "approved" | "rejected",
  { label: string; className: string }
> = {
  // Same tints as the Badge variants: warning / success / danger.
  pending: { label: "Rework in review", className: "border-warning/30 bg-warning/10 text-warning" },
  approved: { label: "Rework approved", className: "border-success/30 bg-success/10 text-success" },
  rejected: {
    label: "Rework rejected - action required",
    className: "border-destructive/30 bg-destructive/10 text-destructive",
  },
};

// Status cell grid: Status | Mode (AUTO or Split) | R, each a fixed width sized
// to its widest content ("Submitted"/"Requested", "AUTO", the 20px circle).
const STATUS_SLOTS = "grid grid-cols-[6.25rem_3.25rem_1.25rem] items-center gap-1.5";

/** Round "R" marker: the report's rework state. Renders nothing when there is none. */
function ReworkMarker({ tasks }: { tasks: WorkReport["tasks"] }) {
  const state = reportReworkState(tasks);
  if (!state) return null;
  const m = REWORK_MARKER[state];
  return (
    <span
      title={m.label}
      aria-label={m.label}
      className={`inline-flex h-5 w-5 items-center justify-center rounded-full border text-[10px] font-bold ${m.className}`}
    >
      R
    </span>
  );
}

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
            <TableHead className="w-[14rem]">Status</TableHead>
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
                  onClick={() => {
                    markReportOpenedFromList(r.id);
                    router.push(`/work-reports/${r.id}`);
                  }}
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
                    {/* Three fixed slots - Status | Mode | R - so the R marker
                        sits at the same x in every row. AUTO and Split are
                        mutually exclusive report types and share the one mode
                        slot; a normal report leaves it empty. */}
                    <span className={STATUS_SLOTS}>
                      <span className="flex">
                        <StatusBadge status={r.status} editRequested={!!r.edit_requested_at} />
                      </span>
                      <span className="flex">
                        <AutoBadge origin={r.origin} />
                        {r.report_mode === "split_day" && (
                          <Badge variant="neutral">Split</Badge>
                        )}
                      </span>
                      <span className="flex">
                        <ReworkMarker tasks={r.tasks} />
                      </span>
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
