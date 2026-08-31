"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { EmptyState } from "@/components/feedback/empty-state";
import { Pagination } from "@/components/data/pagination";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useUrlState } from "@/lib/use-url-state";

import { useLeaveList } from "../hooks";
import {
  LEAVE_TYPE_LABEL,
  canCancelLeave,
  canRequestLeaveCancellation,
  leaveDetailHref,
  type LeaveRequest,
} from "../types";
import { LeaveCancelDialog, type CancelDialogMode } from "./leave-cancel-dialog";
import { LeaveStatusBadge } from "./leave-status-badge";

const LIMIT = 10;

interface Props {
  employeeId?: string;
}

/** Employee leave history with cancel action for pending requests. */
export function LeaveHistory({ employeeId }: Props) {
  const router = useRouter();
  // Page persists in the URL (namespaced lh_*) so returning from a leave detail
  // page keeps the same page.
  const [offsetStr, setOffsetStr] = useUrlState("lh_offset", "0");
  const offset = Math.max(0, Number(offsetStr) || 0);
  const query = useLeaveList({
    employee_id: employeeId,
    limit: LIMIT,
    offset,
  });
  const [dialog, setDialog] = React.useState<
    { request: LeaveRequest; mode: CancelDialogMode } | null
  >(null);

  if (query.isLoading) return <TableSkeleton rows={4} cols={5} />;

  const items = query.data?.items ?? [];
  if (items.length === 0) {
    return (
      <EmptyState
        title="No leave requests"
        description="Your leave requests will appear here once you submit one."
      />
    );
  }

  return (
    <div className="space-y-3">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Type</TableHead>
            <TableHead>From</TableHead>
            <TableHead>To</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Reason</TableHead>
            <TableHead>Manager note</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((req) => (
            <TableRow
              key={req.id}
              className="cursor-pointer hover:bg-muted/40"
              // My leave's own address, so "← Leave" comes back HERE - the same
              // mechanism the approval queues use, with no view of its own.
              onClick={() =>
                router.push(
                  leaveDetailHref(
                    req.id,
                    `${window.location.pathname}${window.location.search}`,
                  ),
                )
              }
            >
              <TableCell className="font-medium">
                {LEAVE_TYPE_LABEL[req.leave_type]}
              </TableCell>
              <TableCell className="tabular">{req.start_date}</TableCell>
              <TableCell className="tabular">{req.end_date}</TableCell>
              <TableCell>
                <LeaveStatusBadge status={req.status} />
              </TableCell>
              <TableCell className="max-w-[200px] truncate text-muted-foreground">
                {req.reason ?? "—"}
              </TableCell>
              <TableCell className="max-w-[200px] truncate text-muted-foreground">
                {req.manager_comment ?? "—"}
              </TableCell>
              <TableCell onClick={(e) => e.stopPropagation()}>
                {canCancelLeave(req, employeeId) ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => setDialog({ request: req, mode: "cancel" })}
                  >
                    Cancel Request
                  </Button>
                ) : canRequestLeaveCancellation(req, employeeId) ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => setDialog({ request: req, mode: "request" })}
                  >
                    Request Cancellation
                  </Button>
                ) : req.status === "cancellation_requested" ? (
                  <span className="text-xs text-muted-foreground">
                    Awaiting PM review
                  </span>
                ) : null}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {(query.data?.total ?? 0) > LIMIT && (
        <Pagination
          total={query.data?.total ?? 0}
          limit={LIMIT}
          offset={offset}
          onPageChange={(o) => setOffsetStr(String(o))}
        />
      )}

      {dialog && (
        <LeaveCancelDialog
          request={dialog.request}
          mode={dialog.mode}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  );
}
