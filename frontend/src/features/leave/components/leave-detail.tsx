"use client";

import * as React from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, Check, ExternalLink, X } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { useAuth } from "@/features/auth/auth-provider";
import { DeliverableStatusBadge } from "@/features/project-deliverables/components/status-badge";
import type { DeliverableStatus } from "@/features/project-deliverables/types";
import { useReportScope } from "@/features/work-reports/hooks";
import { AppError } from "@/lib/api-client";

import {
  useApproveLeave,
  useDeliverableImpact,
  useLeaveRequest,
  useRejectLeave,
} from "../hooks";
import {
  canRequestLeaveCancellation,
  canReviewLeave,
  LEAVE_RETURN_PARAM,
  leaveActorRows,
  leaveRequestDuration,
  leaveReturnHref,
  leaveReturnLabel,
  leaveTypeLabel,
  type DeliverableConflict,
  type LeaveRequest,
} from "../types";
import { LeaveCancelDialog } from "./leave-cancel-dialog";
import { LeaveStatusBadge } from "./leave-status-badge";

const IMPACT_REASON =
  "Please review the project schedule before approving the leave request.";

// ── helpers ─────────────────────────────────────────────────────────────────

function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const d = m
    ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
    : new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function fmtDateTime(value: string | null | undefined): string {
  if (!value) return "—";
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

// ── conflicting deliverable card ─────────────────────────────────────────────

function ConflictCard({ c }: { c: DeliverableConflict }) {
  const router = useRouter();
  return (
    <div className="rounded-lg border border-border bg-card px-4">
      <div className="divide-y divide-border">
        <InfoRow label="Project" value={c.project_code ?? "—"} />
        <InfoRow label="Activity / Deliverable" value={c.deliverable_name} />
        <InfoRow
          label="Status"
          value={<DeliverableStatusBadge status={c.status as DeliverableStatus} />}
        />
        <InfoRow label="Planned Delivery Date" value={fmtDate(c.target_date)} />
      </div>
      <div className="pb-3 pt-1">
        <Button
          size="sm"
          variant="secondary"
          onClick={() => router.push(`/projects/deliverables/${c.deliverable_id}`)}
        >
          <ExternalLink className="h-3.5 w-3.5" />
          Open Deliverable
        </Button>
      </div>
    </div>
  );
}

// ── review panel ─────────────────────────────────────────────────────────────

/**
 * The right half of the detail page: Approve / Reject.
 *
 * RENDERED ONLY WHEN THERE IS A DECISION TO MAKE. The page mounts this behind
 * `canReviewLeave`, so a non-reviewer, an employee looking at their own request
 * and any settled request get no Review card in the DOM at all - not a disabled
 * one, and not one explaining why it is empty. A card that only ever restated
 * the status the Leave Request panel and the page header already show was a
 * third copy of the same fact.
 *
 * The decision itself is the one the Pending-requests queue already makes:
 * the same `useApproveLeave` / `useRejectLeave` mutations, the same optional
 * note, the same toasts. Nothing about approval, authorisation, audit, email or
 * the request body is decided here - this is the queue's interaction rendered in
 * a card instead of a table row, laid out like the Permission Request Review
 * section so the two read alike.
 *
 * `onDone` is what returns the reviewer to the queue they came from. The panel
 * does not know or choose that destination; the page passes the href it already
 * resolved from `?from`, so Pending requests -> Approve -> Pending requests
 * follows from the SAME parameter the "← Leave Requests" link has always used.
 */
function ReviewPanel({ id, onDone }: { id: string; onDone: () => void }) {
  const approve = useApproveLeave();
  const reject = useRejectLeave();
  const [action, setAction] = React.useState<"approve" | "reject" | null>(null);
  const [comment, setComment] = React.useState("");
  const busy = approve.isPending || reject.isPending;

  async function confirm() {
    if (!action) return;
    try {
      if (action === "approve") {
        await approve.mutateAsync({ id, body: { comment: comment || null } });
        toast.success("Leave request approved");
      } else {
        await reject.mutateAsync({ id, body: { comment: comment || null } });
        toast.success("Leave request rejected");
      }
      setAction(null);
      setComment("");
      onDone();
    } catch (err) {
      toast.error(
        err instanceof AppError ? err.message : `Could not ${action} the request.`,
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
          <Button
            variant="secondary"
            onClick={() => {
              setAction("approve");
              setComment("");
            }}
            disabled={busy}
          >
            <Check className="h-4 w-4" />
            Approve
          </Button>
          <Button
            variant="danger"
            onClick={() => {
              setAction("reject");
              setComment("");
            }}
            disabled={busy}
          >
            <X className="h-4 w-4" />
            Reject
          </Button>
        </div>

        {action && (
          <div className="flex items-start gap-2 rounded-lg border border-border bg-secondary/30 p-3">
            <Textarea
              className="text-sm"
              rows={2}
              placeholder={
                action === "approve"
                  ? "Note (optional)"
                  : "Reason for rejection (optional)"
              }
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />
            <div className="flex shrink-0 flex-col gap-1">
              <Button
                size="sm"
                variant={action === "approve" ? "secondary" : "danger"}
                onClick={() => void confirm()}
                loading={busy}
              >
                {action === "approve" ? "Confirm approve" : "Confirm reject"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setAction(null)}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// NO cancellation-request card on this page, of any kind.
//
// It carried Approve cancellation / Keep approved leave, which duplicated the
// Cancellation requests queue's own Actions column; the card is now gone
// entirely, explanatory text included. The queue is the single place a
// withdrawal is both described and decided. Everything else about a withdrawn
// request still shows here through the ordinary Leave Request card: the
// Cancellation Requested status badge, the dates, the Type, the routing rows.
//
// Nothing about the workflow changed. The endpoints, `canReviewLeaveCancellation`
// (still read by the queue) and the server's own `_assert_can_review` are all
// untouched - a card was never authorisation.

// ── page ─────────────────────────────────────────────────────────────────────

export function LeaveDetail({ id }: { id: string }) {
  const router = useRouter();
  const { role, employee, employeeId } = useAuth();
  const isManager = role === "project_manager";

  // Head-ness is not a role - it is per-project and comes from the report
  // scope, exactly as the Leave tab decides whether to show a Head the approval
  // queues (`leave-tab.tsx`). Same fact, same source, so a Head who opens a
  // request from their own Team approvals queue can act on it here too.
  const { data: scope } = useReportScope({ enabled: !isManager });
  const isProjectHead = !isManager && scope?.is_project_head === true;

  const query = useLeaveRequest(id);
  const { byId } = useEmployeeOptions();

  // The Leave list that opened this page, as it looked at the time - so the
  // link below returns to Team approvals / Pending, or to My leave, or to
  // whichever queue it actually came from. A page reached cold (an email link,
  // a bookmark) carries no `from` and falls back to the plain Leave tab, which
  // is exactly what this link has always done.
  const searchParams = useSearchParams();
  const rawFrom = searchParams.get(LEAVE_RETURN_PARAM);
  const backHref = leaveReturnHref(rawFrom);
  // The link SAYS where it goes. Opened from Cancellation requests it reads
  // "← Cancellation Requests"; from anywhere else it is the "← Leave Requests" it
  // has always been. Off the resolved href, never the raw parameter.
  const backLabel = leaveReturnLabel(rawFrom);

  // The employee's own "ask to withdraw this" confirmation, the SAME dialog My
  // leave opens from its Request Cancellation button - not a second one written
  // for this page.
  const [cancelDialogOpen, setCancelDialogOpen] = React.useState(false);

  // Deliverable conflicts are PM-only decision support; the endpoint rejects
  // non-managers, so only query for managers.
  const impactQuery = useDeliverableImpact(isManager ? [id] : []);
  const conflicts =
    impactQuery.data?.items.find((i) => i.leave_request_id === id)?.conflicts ?? [];

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
    const notFound = query.error instanceof AppError && query.error.status === 404;
    return (
      <ErrorState
        title={notFound ? "Leave request not found" : "Couldn't load leave request"}
        message={
          notFound
            ? "This leave request may have been removed."
            : "Please try again."
        }
        onRetry={notFound ? undefined : () => void query.refetch()}
      />
    );
  }

  const leave = query.data;
  // The SERVER-resolved name first. `byId` comes from `GET /employees`, which is
  // RBAC-scoped and returns only their own row to a plain employee-role actor -
  // which a Project Head still is - so reading it first meant a Head opening a
  // colleague's request fell all the way through to eight characters of a UUID.
  // The backend has always sent `employee_name` on this response; it just was
  // not being read. The remaining fallbacks are kept for the responses that
  // carry no name (a mutation's) rather than removed.
  const empName =
    leave.employee_name ??
    byId.get(leave.employee_id) ??
    (leave.employee_id === employeeId ? employee?.full_name : undefined) ??
    leave.employee_id.slice(0, 8);
  const showImpact = isManager && conflicts.length > 0;
  const isReviewer = isManager || isProjectHead;
  const canReview = canReviewLeave(leave, isReviewer, employeeId);
  // The owner's half of the cancellation workflow, and the only half this page
  // carries: asking to withdraw approved leave, offered here exactly as it
  // always was. It does not consult `half_day_period` - a half day is withdrawn
  // exactly as a full day is - and the backend enforces the rule independently.
  // The reviewer's half lives in the Cancellation requests queue.
  const showRequestCancellation = canRequestLeaveCancellation(leave, employeeId);
  // What the card SAYS about the request's routing and its actor - two separate
  // facts, both shown on a settled request. Independent of `canReview`, which
  // decides what this reader may DO: the request owner sees these rows and still
  // gets no Review card.
  const actorRows = leaveActorRows(leave);

  return (
    <>
      <Link
        href={backHref}
        className="text-sm text-primary hover:underline"
      >
        {backLabel}
      </Link>
      {/* No status badge here. The Leave Request card below carries the one
          Status row this page shows - a badge in the header repeated it. */}
      <PageHeader
        className="mt-2"
        title={empName}
        subtitle={`${leaveTypeLabel(leave)} leave`}
      />

      <div className="space-y-4">
        {/* Leave request + review, side by side (stacked below lg).
            The two columns are ALWAYS there on desktop: Leave Request keeps the
            left half whether or not there is a Review card to put beside it, so
            the card does not change width with the reader. With no reviewer the
            right column is simply empty - no placeholder card, no text. */}
        <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
          <Card>
            <CardHeader>
              <CardTitle>Leave Request</CardTitle>
            </CardHeader>
            <CardContent className="divide-y divide-border">
              <InfoRow label="Employee" value={empName} />
              {/* Half Day (First)/(Second) when the request carries a half,
                  otherwise the Normal/Special classification - one precedence,
                  shared with every list and with the emails. */}
              <InfoRow label="Leave Type" value={leaveTypeLabel(leave)} />
              <InfoRow label="Requested On" value={fmtDateTime(leave.created_at)} />
              <InfoRow label="From" value={fmtDate(leave.start_date)} />
              <InfoRow label="To" value={fmtDate(leave.end_date)} />
              {/* `0.5 day` for a half day. A half-day request covers one
                  working day, so the raw count reads "1 day" and understates
                  nothing but the half the employee actually took. */}
              <InfoRow label="Duration" value={leaveRequestDuration(leave)} />
              <InfoRow label="Status" value={<LeaveStatusBadge status={leave.status} />} />
              {/* Routed to, then Approved by / Rejected by - a settled request
                  shows both, because who it went to and who ruled on it are
                  different questions with frequently different answers.
                  Informational only: never what this reader may do, which stays
                  `canReviewLeave` below. Absent entirely for a cancelled request,
                  whose cancelling actor the system does not record. */}
              {actorRows.map((row) => (
                <InfoRow key={row.label} label={row.label} value={row.name} />
              ))}
              {leave.manager_comment ? (
                <InfoRow label="Note" value={leave.manager_comment} />
              ) : null}
            </CardContent>
          </Card>

          {canReview && (
            <ReviewPanel
              id={leave.id}
              // Back to the queue this page was opened from - the same href
              // "← Leave Requests" uses, resolved from the same `?from`. Approving out of
              // Pending requests therefore lands back on Pending requests, and a
              // cold-opened page falls back to the Leave tab exactly as before.
              onDone={() => router.push(backHref)}
            />
          )}
        </div>

        {/* Deliverable impact — full width, below the split */}
        {showImpact && (
          <Card className="border-warning/40">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-warning">
                <AlertTriangle className="h-4 w-4" />
                Deliverable Impact
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">{IMPACT_REASON}</p>
              <div className="space-y-2.5">
                {conflicts.map((c) => (
                  <ConflictCard key={c.deliverable_id} c={c} />
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* The owner's own side of the same workflow: approved leave is a granted
            absence, so withdrawing it is a request a reviewer decides, not a
            one-click cancel. Offered here as well as in My leave, so the page a
            reader opens to check their leave is the page they can act on. */}
        {showRequestCancellation && (
          <Card>
            <CardHeader>
              <CardTitle>Withdraw</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                This leave is approved, so withdrawing it needs a reviewer&apos;s
                decision. It stays approved until they rule on your request.
              </p>
              <Button
                variant="secondary"
                onClick={() => setCancelDialogOpen(true)}
              >
                Request Cancellation
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Reason — the SAME grid as the block above, so it takes the left half
            and its edges line up with the Leave Request card rather than running
            the full width. Below lg it stacks and fills, exactly as that block
            does; the right half stays empty. */}
        <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
          <Card>
            <CardHeader>
              <CardTitle>Reason</CardTitle>
            </CardHeader>
            <CardContent>
              {leave.reason?.trim() ? (
                <p className="whitespace-pre-wrap text-sm">{leave.reason}</p>
              ) : (
                <p className="text-sm text-muted-foreground">No reason provided.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {cancelDialogOpen && (
        <LeaveCancelDialog
          request={leave}
          mode="request"
          onClose={() => setCancelDialogOpen(false)}
        />
      )}
    </>
  );
}
