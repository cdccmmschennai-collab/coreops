"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Check, X } from "lucide-react";
import { toast } from "sonner";

import { EmptyState } from "@/components/feedback/empty-state";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import { Badge } from "@/components/ui/badge";
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

import { useApproveLeave, useDeliverableImpact, useLeaveList, useRejectLeave } from "../hooks";
import { LEAVE_TYPE_LABEL, type DeliverableConflict } from "../types";

const COL_COUNT = 7;

interface Props {
  /** If set, only show requests for this employee's team. Admin: leave undefined for all. */
  employeeId?: string;
}

/** Manager / Admin panel: pending requests with approve/reject actions.
 *  Clicking a row opens the leave detail page (full reason + deliverable impact). */
export function LeaveReviewPanel({ employeeId: _eid }: Props) {
  const router = useRouter();
  const pendingQuery = useLeaveList({ status: "pending", limit: 50, offset: 0 });
  const approve = useApproveLeave();
  const reject = useRejectLeave();
  const { byId: empById } = useEmployeeOptions();

  const pending = pendingQuery.data?.items ?? [];
  const pendingIds = React.useMemo(() => pending.map((r) => r.id), [pending]);

  // One bulk call flags which displayed rows overlap a planned deliverable.
  const impactQuery = useDeliverableImpact(pendingIds);
  const impactByLeave = React.useMemo(() => {
    const map = new Map<string, DeliverableConflict[]>();
    for (const item of impactQuery.data?.items ?? []) {
      map.set(item.leave_request_id, item.conflicts);
    }
    return map;
  }, [impactQuery.data]);

  // Approve and Reject both open the same inline note form (note optional for
  // either decision); `action` tracks which row + which decision is open.
  const [action, setAction] = React.useState<
    { id: string; type: "approve" | "reject" } | null
  >(null);
  const [comment, setComment] = React.useState("");
  const busy = approve.isPending || reject.isPending;

  function startAction(id: string, type: "approve" | "reject") {
    setAction({ id, type });
    setComment("");
  }

  function cancelAction() {
    setAction(null);
    setComment("");
  }

  async function confirmAction() {
    if (!action) return;
    const { id, type } = action;
    try {
      if (type === "approve") {
        await approve.mutateAsync({ id, body: { comment: comment || null } });
        toast.success("Leave request approved");
      } else {
        await reject.mutateAsync({ id, body: { comment: comment || null } });
        toast.success("Leave request rejected");
      }
      cancelAction();
    } catch (err) {
      toast.error(
        err instanceof AppError
          ? err.message
          : `Could not ${type} the request.`,
      );
    }
  }

  if (pendingQuery.isLoading) return <TableSkeleton rows={3} cols={COL_COUNT} />;

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
                <TableHead>Deliverable Impact</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pending.map((req) => {
                const hasImpact = (impactByLeave.get(req.id) ?? []).length > 0;
                const empName =
                  empById.get(req.employee_id) ?? req.employee_id.slice(0, 8);
                return (
                  <React.Fragment key={req.id}>
                    <TableRow
                      className="cursor-pointer hover:bg-muted/40"
                      onClick={() => router.push(`/attendance/leave/${req.id}`)}
                    >
                      <TableCell className="font-medium">{empName}</TableCell>
                      <TableCell>{LEAVE_TYPE_LABEL[req.leave_type]}</TableCell>
                      <TableCell className="tabular">{req.start_date}</TableCell>
                      <TableCell className="tabular">{req.end_date}</TableCell>
                      <TableCell className="max-w-[180px] truncate text-muted-foreground">
                        {req.reason ?? "—"}
                      </TableCell>
                      <TableCell>
                        {hasImpact ? (
                          <Badge variant="warning">
                            <AlertTriangle className="h-3 w-3" />
                            Deliverable
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <div
                          className="flex items-center gap-1"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => startAction(req.id, "approve")}
                            disabled={busy}
                          >
                            <Check className="h-3.5 w-3.5" />
                            Approve
                          </Button>
                          <Button
                            size="sm"
                            variant="danger"
                            onClick={() => startAction(req.id, "reject")}
                            disabled={busy}
                          >
                            <X className="h-3.5 w-3.5" />
                            Reject
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>

                    {action?.id === req.id && (
                      <TableRow className="hover:bg-transparent">
                        <TableCell colSpan={COL_COUNT} className="bg-secondary/30 px-5 py-3">
                          <div
                            className="flex items-start gap-2"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <Textarea
                              className="text-sm"
                              rows={2}
                              placeholder={
                                action.type === "approve"
                                  ? "Note (optional)"
                                  : "Reason for rejection (optional)"
                              }
                              value={comment}
                              onChange={(e) => setComment(e.target.value)}
                            />
                            <div className="flex flex-col gap-1 shrink-0">
                              <Button
                                size="sm"
                                variant={action.type === "approve" ? "secondary" : "danger"}
                                onClick={() => void confirmAction()}
                                loading={busy}
                              >
                                {action.type === "approve"
                                  ? "Confirm approve"
                                  : "Confirm reject"}
                              </Button>
                              <Button size="sm" variant="ghost" onClick={cancelAction}>
                                Cancel
                              </Button>
                            </div>
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </React.Fragment>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
