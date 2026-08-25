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
import { AppError } from "@/lib/api-client";

import {
  useApproveContinuationRequest,
  usePendingContinuationRequests,
  useRejectContinuationRequest,
} from "../hooks";
import { ContinuationStatusBadge } from "./continuation-status-badge";

const COL_COUNT = 9;

export function ContinuationReviewPanel() {
  const router = useRouter();
  const pendingQuery = usePendingContinuationRequests();
  const approve = useApproveContinuationRequest();
  const reject = useRejectContinuationRequest();
  const pending = pendingQuery.data ?? [];

  const [action, setAction] = React.useState<{ id: string; type: "approve" | "reject" } | null>(
    null,
  );
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
        toast.success("Continuation approved");
      } else {
        await reject.mutateAsync({ id, body: { comment: comment || null } });
        toast.success("Continuation rejected");
      }
      cancelAction();
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : `Could not ${type} the request.`);
    }
  }

  if (pendingQuery.isLoading) return <TableSkeleton rows={3} cols={COL_COUNT} />;

  return (
    <Card>
      <CardHeader className="border-b border-border px-5 py-3.5">
        <CardTitle className="text-base flex items-center gap-2">
          Pending requests
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
              description="All continuation requests have been reviewed."
            />
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Employee</TableHead>
                <TableHead>Project</TableHead>
                <TableHead>Activity</TableHead>
                <TableHead>Sub-Activity</TableHead>
                <TableHead>Original Date</TableHead>
                <TableHead>Allowed Duration</TableHead>
                <TableHead>Continuation Date</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pending.map((req) => (
                <React.Fragment key={req.id}>
                  <TableRow
                    className="cursor-pointer hover:bg-muted/40"
                    onClick={() => router.push(`/lump-sum-activity/${req.id}`)}
                  >
                    <TableCell className="font-medium">{req.employee_name}</TableCell>
                    <TableCell>{req.project_code || req.project_name}</TableCell>
                    <TableCell>{req.activity_name ?? "-"}</TableCell>
                    <TableCell>{req.sub_activity_name}</TableCell>
                    <TableCell className="tabular">{req.original_report_date}</TableCell>
                    <TableCell className="tabular">
                      {req.allowed_duration_days} {req.allowed_duration_days === 1 ? "day" : "days"}
                    </TableCell>
                    <TableCell className="tabular">{req.continuation_date}</TableCell>
                    <TableCell>
                      <ContinuationStatusBadge status={req.status} />
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
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
                              {action.type === "approve" ? "Confirm approve" : "Confirm reject"}
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
