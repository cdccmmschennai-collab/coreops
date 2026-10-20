"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Check, X } from "lucide-react";
import { toast } from "sonner";

import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
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

import { useApproveCompOff, useCompOffList, useRejectCompOff } from "../hooks";
import {
  canDecide,
  compOffDetailHref,
  compOffErrorMessage,
  formatShortDate,
  rejectionReasonError,
  type CompOffViewer,
} from "../types";

const COL_COUNT = 6;

/** The project manager's pending comp off queue - the same shape as the
 *  permission queue: one table, an inline note form, two buttons.
 *
 *  Own requests are dropped SERVER-side (`exclude_self`), and the backend
 *  re-checks authority, the self-review rule and every eligibility rule under a
 *  lock on each decision, so this panel only reports what the server refuses.
 *  A 409 or 422 never reads as success and is never retried automatically. */
export function CompOffReviewPanel({ viewer }: { viewer: CompOffViewer }) {
  const router = useRouter();
  const query = useCompOffList({ status: "pending", limit: 50, offset: 0, exclude_self: true });
  const approve = useApproveCompOff();
  const reject = useRejectCompOff();

  const pending = (query.data?.items ?? []).filter((r) => canDecide(r, viewer));
  const [action, setAction] = React.useState<{ id: string; type: "approve" | "reject" } | null>(
    null,
  );
  const [comment, setComment] = React.useState("");
  const [reasonError, setReasonError] = React.useState<string | null>(null);
  const busy = approve.isPending || reject.isPending;

  function startAction(id: string, type: "approve" | "reject") {
    setAction({ id, type });
    setComment("");
    setReasonError(null);
  }

  function cancelAction() {
    setAction(null);
    setComment("");
    setReasonError(null);
  }

  async function confirmAction() {
    if (!action || busy) return;
    const { id, type } = action;
    if (type === "reject") {
      const problem = rejectionReasonError(comment);
      setReasonError(problem);
      if (problem) return;
    }
    try {
      if (type === "approve") {
        await approve.mutateAsync({ id, body: { comment: comment.trim() || null } });
        toast.success("Comp off approved - the day off is marked in attendance");
      } else {
        await reject.mutateAsync({ id, body: { reason: comment.trim() } });
        toast.success("Comp off request rejected");
      }
      cancelAction();
    } catch (err) {
      const verb = type === "approve" ? "approve the request" : "reject the request";
      toast.error(
        err instanceof AppError
          ? compOffErrorMessage(err.status, err.message, verb)
          : compOffErrorMessage(undefined, undefined, verb),
      );
      // A 409 means someone else decided it - re-read so the row reflects that.
      if (err instanceof AppError && err.status === 409) void query.refetch();
    }
  }

  if (query.isLoading) return <TableSkeleton rows={3} cols={COL_COUNT} />;

  return (
    <Card>
      <CardHeader className="border-b border-border px-5 py-3.5">
        <CardTitle className="flex items-center gap-2 text-base">
          Pending comp off requests
          {pending.length > 0 && (
            <span className="rounded-full bg-warning/15 px-2 py-0.5 text-[11px] font-semibold text-warning">
              {pending.length}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {query.isError ? (
          <ErrorState
            title="Couldn't load pending requests"
            message="Check your connection and try again."
            onRetry={() => void query.refetch()}
          />
        ) : pending.length === 0 ? (
          <div className="px-5 py-8">
            <EmptyState
              title="No pending requests"
              description="All comp off requests have been reviewed."
            />
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Employee</TableHead>
                <TableHead>Day worked</TableHead>
                <TableHead>Day off</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Requested</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pending.map((req) => (
                <React.Fragment key={req.id}>
                  {/* The row opens the detail page (full reason, decision card);
                      the action cell stops propagation so deciding in place
                      still works without navigating away - as the leave and
                      permission queues do. */}
                  <TableRow
                    className="cursor-pointer hover:bg-muted/40"
                    onClick={() => router.push(compOffDetailHref(req.id))}
                  >
                    <TableCell className="font-medium">
                      {req.employee_name ?? req.employee_id.slice(0, 8)}
                    </TableCell>
                    <TableCell className="tabular">{formatShortDate(req.worked_date)}</TableCell>
                    <TableCell className="tabular">{formatShortDate(req.off_date)}</TableCell>
                    <TableCell className="max-w-[220px] truncate text-muted-foreground">
                      {req.reason ?? "-"}
                    </TableCell>
                    <TableCell className="tabular text-muted-foreground">
                      {formatShortDate(req.created_at)}
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
                        {action.type === "approve" && (
                          <p className="mb-2 text-sm text-muted-foreground">
                            Approving marks {formatShortDate(req.off_date)} as Comp off in
                            attendance. The server checks the work report for{" "}
                            {formatShortDate(req.worked_date)} again before it does.
                          </p>
                        )}
                        <div className="flex items-start gap-2">
                          <div className="flex-1 space-y-1">
                            <Textarea
                              className="text-sm"
                              rows={2}
                              aria-label={
                                action.type === "approve" ? "Approval note" : "Reason for rejection"
                              }
                              aria-invalid={Boolean(reasonError)}
                              placeholder={
                                action.type === "approve"
                                  ? "Note (optional)"
                                  : "Reason for rejection (required)"
                              }
                              value={comment}
                              onChange={(e) => {
                                setComment(e.target.value);
                                if (reasonError) setReasonError(null);
                              }}
                              autoFocus
                            />
                            {reasonError && (
                              <p className="text-sm text-destructive" role="alert">
                                {reasonError}
                              </p>
                            )}
                          </div>
                          <div className="flex shrink-0 flex-col gap-1">
                            <Button
                              size="sm"
                              variant={action.type === "approve" ? "secondary" : "danger"}
                              onClick={() => void confirmAction()}
                              loading={busy}
                              disabled={busy}
                            >
                              {action.type === "approve" ? "Confirm approve" : "Confirm reject"}
                            </Button>
                            <Button size="sm" variant="ghost" onClick={cancelAction} disabled={busy}>
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
