"use client";

import * as React from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, X } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/features/auth/auth-provider";
import { AppError } from "@/lib/api-client";

import { useApproveCompOff, useCompOffRequest, useRejectCompOff } from "../hooks";
import {
  COMP_OFF_TAB_HREF,
  canDecide,
  compOffErrorMessage,
  decidedByLabel,
  formatShortDate,
  rejectionReasonError,
  type CompOffRequest,
} from "../types";
import { CompOffStatusBadge } from "./comp-off-status-badge";

function fmtDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function InfoRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

/** Approve / Reject - the queue's decision rendered as a card, laid out like
 *  the leave detail's Review card. Mounted only when there is a decision this
 *  reader may make; the server re-checks authority and eligibility either way. */
function ReviewPanel({ req, onDone }: { req: CompOffRequest; onDone: () => void }) {
  const approve = useApproveCompOff();
  const reject = useRejectCompOff();
  const [action, setAction] = React.useState<"approve" | "reject" | null>(null);
  const [comment, setComment] = React.useState("");
  const [reasonError, setReasonError] = React.useState<string | null>(null);
  const busy = approve.isPending || reject.isPending;

  function start(type: "approve" | "reject") {
    setAction(type);
    setComment("");
    setReasonError(null);
  }

  async function confirm() {
    if (!action || busy) return;
    if (action === "reject") {
      const problem = rejectionReasonError(comment);
      setReasonError(problem);
      if (problem) return;
    }
    try {
      if (action === "approve") {
        await approve.mutateAsync({ id: req.id, body: { comment: comment.trim() || null } });
        toast.success("Comp off approved - the day off is marked in attendance");
      } else {
        await reject.mutateAsync({ id: req.id, body: { reason: comment.trim() } });
        toast.success("Comp off request rejected");
      }
      onDone();
    } catch (err) {
      const verb = action === "approve" ? "approve the request" : "reject the request";
      toast.error(
        err instanceof AppError
          ? compOffErrorMessage(err.status, err.message, verb)
          : compOffErrorMessage(undefined, undefined, verb),
      );
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Review</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => start("approve")} disabled={busy}>
            <Check className="h-4 w-4" />
            Approve
          </Button>
          <Button variant="danger" onClick={() => start("reject")} disabled={busy}>
            <X className="h-4 w-4" />
            Reject
          </Button>
        </div>

        {action && (
          <div className="space-y-2 rounded-lg border border-border bg-secondary/30 p-3">
            {action === "approve" && (
              <p className="text-sm text-muted-foreground">
                Approving marks {formatShortDate(req.off_date)} as Comp off in attendance.
              </p>
            )}
            <div className="flex items-start gap-2">
              <div className="flex-1 space-y-1">
                <Textarea
                  className="text-sm"
                  rows={2}
                  aria-label={action === "approve" ? "Approval note" : "Reason for rejection"}
                  aria-invalid={Boolean(reasonError)}
                  placeholder={
                    action === "approve" ? "Note (optional)" : "Reason for rejection (required)"
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
                  variant={action === "approve" ? "secondary" : "danger"}
                  onClick={() => void confirm()}
                  loading={busy}
                  disabled={busy}
                >
                  {action === "approve" ? "Confirm approve" : "Confirm reject"}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setAction(null)} disabled={busy}>
                  Cancel
                </Button>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** One comp off request: the request, its decision, and - for a project
 *  manager who may decide it - the Review card. The server allows a PM or the
 *  request's author to read it; anyone else gets the 403 error state. */
export function CompOffDetail({ id }: { id: string }) {
  const router = useRouter();
  const { role, employeeId } = useAuth();
  const query = useCompOffRequest(id);

  if (query.isLoading) {
    return (
      <>
        <Skeleton className="mb-6 h-10 w-64" />
        <div className="space-y-4">
          <Skeleton className="h-48" />
          <Skeleton className="h-24" />
        </div>
      </>
    );
  }

  if (query.isError || !query.data) {
    const status = query.error instanceof AppError ? query.error.status : undefined;
    return (
      <ErrorState
        title={
          status === 404
            ? "Comp off request not found"
            : status === 403
              ? "You can't view this request"
              : "Couldn't load comp off request"
        }
        message={
          status === 404
            ? "This comp off request may have been removed."
            : status === 403
              ? "You can only view your own comp off requests."
              : "Please try again."
        }
        onRetry={status === 404 || status === 403 ? undefined : () => void query.refetch()}
      />
    );
  }

  const req = query.data;
  const empName = req.employee_name ?? req.employee_id.slice(0, 8);
  const decidedBy = decidedByLabel(req.status);
  const showReview = canDecide(req, { role, employeeId });

  return (
    <>
      <Link href={COMP_OFF_TAB_HREF} className="text-sm text-primary hover:underline">
        ← Comp Off
      </Link>
      <PageHeader className="mt-2" title={empName} subtitle="Comp off request" />

      <div className="space-y-4">
        <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
          <Card>
            <CardHeader>
              <CardTitle>Comp Off Request</CardTitle>
            </CardHeader>
            <CardContent className="divide-y divide-border">
              <InfoRow label="Employee" value={empName} />
              <InfoRow label="Requested On" value={fmtDateTime(req.created_at)} />
              <InfoRow label="Day Worked" value={formatShortDate(req.worked_date)} />
              <InfoRow label="Day Off" value={formatShortDate(req.off_date)} />
              <InfoRow label="Status" value={<CompOffStatusBadge status={req.status} />} />
              {decidedBy && (
                <InfoRow label={decidedBy} value={req.manager_name ?? "-"} />
              )}
              {req.reviewed_at && (
                <InfoRow label="Decided On" value={fmtDateTime(req.reviewed_at)} />
              )}
              {req.manager_comment && (
                <InfoRow
                  label={req.status === "rejected" ? "Rejection Reason" : "Note"}
                  value={req.manager_comment}
                />
              )}
            </CardContent>
          </Card>

          {showReview && (
            <ReviewPanel req={req} onDone={() => router.push(COMP_OFF_TAB_HREF)} />
          )}
        </div>

        <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
          <Card>
            <CardHeader>
              <CardTitle>Reason</CardTitle>
            </CardHeader>
            <CardContent>
              {req.reason?.trim() ? (
                <p className="whitespace-pre-wrap text-sm">{req.reason}</p>
              ) : (
                <p className="text-sm text-muted-foreground">No reason provided.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
