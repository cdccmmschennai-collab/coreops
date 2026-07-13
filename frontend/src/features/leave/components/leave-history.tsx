"use client";

import { useRouter } from "next/navigation";
import { toast } from "sonner";

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
import { AppError } from "@/lib/api-client";
import { useUrlState } from "@/lib/use-url-state";

import { useCancelLeave, useLeaveList } from "../hooks";
import { LEAVE_TYPE_LABEL } from "../types";
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
  const cancel = useCancelLeave();

  async function onCancel(id: string) {
    try {
      await cancel.mutateAsync(id);
      toast.success("Leave request cancelled");
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not cancel request.");
    }
  }

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
              onClick={() => router.push(`/attendance/leave/${req.id}`)}
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
                {req.status === "pending" && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => void onCancel(req.id)}
                    disabled={cancel.isPending}
                  >
                    Cancel
                  </Button>
                )}
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
    </div>
  );
}
