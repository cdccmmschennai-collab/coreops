"use client";

import * as React from "react";
import { Check, X } from "lucide-react";
import { toast } from "sonner";

import { EmptyState } from "@/components/feedback/empty-state";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { AppError } from "@/lib/api-client";

import { useApproveLeave, useLeaveList, useRejectLeave } from "../hooks";
import { LEAVE_TYPE_LABEL } from "../types";
import { LeaveStatusBadge } from "./leave-status-badge";

interface Props {
  /** If set, only show requests for this employee's team. Admin: leave undefined for all. */
  employeeId?: string;
}

/** Manager / Admin panel: shows pending requests with approve/reject actions. */
export function LeaveReviewPanel({ employeeId: _eid }: Props) {
  const pendingQuery = useLeaveList({ status: "pending", limit: 50, offset: 0 });
  const approve = useApproveLeave();
  const reject = useRejectLeave();
  const { byId: empById } = useEmployeeOptions();

  const [rejectingId, setRejectingId] = React.useState<string | null>(null);
  const [comment, setComment] = React.useState("");

  async function onApprove(id: string) {
    try {
      await approve.mutateAsync({ id, body: {} });
      toast.success("Leave request approved");
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not approve.");
    }
  }

  async function onReject(id: string) {
    try {
      await reject.mutateAsync({ id, body: { comment: comment || null } });
      toast.success("Leave request rejected");
      setRejectingId(null);
      setComment("");
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not reject.");
    }
  }

  if (pendingQuery.isLoading) return <TableSkeleton rows={3} cols={6} />;

  const pending = pendingQuery.data?.items ?? [];

  return (
    <Card>
      <CardHeader className="border-b border-border px-5 py-3.5">
        <CardTitle className="text-base flex items-center gap-2">
          Pending leave requests
          {pending.length > 0 && (
            <span className="rounded-full bg-warning/15 px-2 py-0.5 text-[11px] font-semibold text-warning">
              {pending.length}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {pending.length === 0 ? (
          <div className="px-5 py-8">
            <EmptyState
              title="No pending requests"
              description="All leave requests have been reviewed."
            />
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Employee</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>From</TableHead>
                <TableHead>To</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pending.map((req) => (
                <React.Fragment key={req.id}>
                  <TableRow>
                    <TableCell className="font-medium">
                      {empById.get(req.employee_id) ?? req.employee_id.slice(0, 8)}
                    </TableCell>
                    <TableCell>{LEAVE_TYPE_LABEL[req.leave_type]}</TableCell>
                    <TableCell className="tabular">{req.start_date}</TableCell>
                    <TableCell className="tabular">{req.end_date}</TableCell>
                    <TableCell className="max-w-[180px] truncate text-muted-foreground">
                      {req.reason ?? "—"}
                    </TableCell>
                    <TableCell>
                      <LeaveStatusBadge status={req.status} />
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => void onApprove(req.id)}
                          disabled={approve.isPending || reject.isPending}
                        >
                          <Check className="h-3.5 w-3.5" />
                          Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() => {
                            setRejectingId(req.id);
                            setComment("");
                          }}
                          disabled={approve.isPending || reject.isPending}
                        >
                          <X className="h-3.5 w-3.5" />
                          Reject
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                  {rejectingId === req.id && (
                    <TableRow>
                      <TableCell colSpan={7} className="bg-secondary/30 px-5 py-3">
                        <div className="flex items-start gap-2">
                          <Textarea
                            className="text-sm"
                            rows={2}
                            placeholder="Reason for rejection (optional)"
                            value={comment}
                            onChange={(e) => setComment(e.target.value)}
                          />
                          <div className="flex flex-col gap-1 shrink-0">
                            <Button size="sm" variant="danger" onClick={() => void onReject(req.id)}
                              loading={reject.isPending}>
                              Confirm reject
                            </Button>
                            <Button size="sm" variant="ghost"
                              onClick={() => { setRejectingId(null); setComment(""); }}>
                              Cancel
                            </Button>
                          </div>
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </React.Fragment>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
