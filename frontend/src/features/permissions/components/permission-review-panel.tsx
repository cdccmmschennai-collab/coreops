"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
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

import { useApprovePermission, usePermissionList, useRejectPermission } from "../hooks";
import { formatDuration, formatShortDate, permissionDetailPath } from "../types";

const COL_COUNT = 6;

/** The project manager's pending-permission queue, reusing the exact shape of
 *  the pending-leave queue: same table, same inline note form, same two buttons.
 *
 *  Neither the balance guard nor the self-approval guard is implemented here.
 *  Both live in the backend and are re-checked under a lock on every decision, so
 *  this panel simply reports whatever the server refuses. */
export function PermissionReviewPanel() {
  const router = useRouter();
  const pendingQuery = usePermissionList({ status: "pending", limit: 50, offset: 0 });
  const approve = useApprovePermission();
  const reject = useRejectPermission();
  const { byId: empById } = useEmployeeOptions();

  const pending = pendingQuery.data?.items ?? [];

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
        toast.success("Permission request approved");
      } else {
        await reject.mutateAsync({ id, body: { comment: comment || null } });
        toast.success("Permission request rejected");
      }
      cancelAction();
    } catch (err) {
      toast.error(
        err instanceof AppError ? err.message : `Could not ${type} the request.`,
      );
    }
  }

  if (pendingQuery.isLoading) return <TableSkeleton rows={3} cols={COL_COUNT} />;

  return (
    <Card>
      <CardHeader className="border-b border-border px-5 py-3.5">
        <CardTitle className="text-base flex items-center gap-2">
          Pending permission requests
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
              description="All permission requests have been reviewed."
            />
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Employee</TableHead>
                <TableHead>Date</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Requested</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pending.map((req) => (
                <React.Fragment key={req.id}>
                  {/* Row opens the detail page (full reason + balance context);
                      the action cell stops propagation so deciding in place still
                      works without navigating away. */}
                  <TableRow
                    className="cursor-pointer hover:bg-muted/40"
                    onClick={() => router.push(permissionDetailPath(req.id))}
                  >
                    <TableCell className="font-medium">
                      {empById.get(req.employee_id) ?? req.employee_id.slice(0, 8)}
                    </TableCell>
                    <TableCell className="tabular">
                      {formatShortDate(req.permission_date)}
                    </TableCell>
                    <TableCell className="tabular">
                      {formatDuration(req.duration_hours)}
                    </TableCell>
                    <TableCell className="max-w-[220px] truncate text-muted-foreground">
                      {req.reason ?? "-"}
                    </TableCell>
                    <TableCell className="tabular text-muted-foreground">
                      {req.created_at.slice(0, 10)}
                    </TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center gap-1">
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
                        <div className="flex items-start gap-2">
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
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
