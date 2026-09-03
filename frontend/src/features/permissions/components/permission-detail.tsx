"use client";

import * as React from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Check, X } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/features/auth/auth-provider";
import { useReportScope } from "@/features/work-reports/hooks";
import { AppError } from "@/lib/api-client";

import {
  useApprovePermission,
  useApprovePermissionCancellation,
  useCancelPermission,
  usePermissionRequest,
  useRejectPermission,
  useRejectPermissionCancellation,
  useRequestPermissionCancellation,
} from "../hooks";
import {
  PERMISSION_HISTORY_PATH,
  PERMISSION_RETURN_PARAM,
  canCancelPermission,
  canRequestPermissionCancellation,
  canReviewPermission,
  canReviewPermissionCancellation,
  formatHours,
  formatPermissionDuration,
  formatMonthLabel,
  formatShortDate,
  permissionActorRow,
  permissionReturnHref,
  type PermissionRequestDetail as Detail,
} from "../types";
import { PermissionStatusBadge } from "./permission-status-badge";

// ── helpers ─────────────────────────────────────────────────────────────────

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

/** Same row shape as the leave detail page, so the two read alike. */
function InfoRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

// ── balance card ────────────────────────────────────────────────────────────

/**
 * What this request did - or would do - to the month's 4h allowance.
 *
 * Every number is read straight off `detail.balance`, which the backend derives
 * from the same rule as everything else. NOTHING is computed here: a UI that did
 * its own arithmetic would be a second implementation of the allowance rule, and
 * the two would eventually disagree.
 *
 * The wording changes with the status because the facts do. Only an approved
 * request has taken hours; a pending one has an outcome to forecast; a rejected
 * or cancelled one has taken nothing and must not be shown as if it had.
 */
function BalanceCard({ detail }: { detail: Detail }) {
  const b = detail.balance;
  const month = formatMonthLabel(b.month);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Permission balance</CardTitle>
      </CardHeader>
      <CardContent className="divide-y divide-border">
        <InfoRow label="Month" value={month} />
        <InfoRow label="Monthly allowance" value={formatHours(b.allowance_hours)} />

        {/* A permission awaiting a WITHDRAWAL decision still holds its hours, so
            it reports them exactly as an approved one does - `consumed_by_
            request` comes back non-zero for both, from the same server-side
            rule. Saying anything else here would contradict the balance. */}
        {(detail.status === "approved" ||
          detail.status === "cancellation_requested") && (
          <>
            <InfoRow
              label="Before approval"
              value={formatHours(b.remaining_before_request)}
            />
            <InfoRow
              label="Permission taken"
              value={formatHours(b.consumed_by_request)}
            />
            <InfoRow label="Remaining" value={formatHours(b.remaining_hours)} />
            {detail.status === "cancellation_requested" && (
              <InfoRow
                label="Cancellation"
                value={
                  <span className="text-muted-foreground">
                    Requested - the hours return only if it is approved
                  </span>
                }
              />
            )}
          </>
        )}

        {detail.status === "pending" && (
          <>
            <InfoRow label="Available now" value={formatHours(b.remaining_hours)} />
            <InfoRow
              label="Remaining after approval"
              value={
                b.remaining_if_approved === null
                  ? "-"
                  : formatHours(b.remaining_if_approved)
              }
            />
            <InfoRow
              label="Taken by this request"
              value={
                <span className="text-muted-foreground">
                  Nothing yet - pending requests don&apos;t use the allowance
                </span>
              }
            />
          </>
        )}

        {(detail.status === "rejected" || detail.status === "cancelled") && (
          <>
            <InfoRow
              label="Taken by this request"
              value={
                <span className="text-muted-foreground">
                  {detail.status === "rejected"
                    ? "Nothing - the request was rejected"
                    : "Nothing - the hours were restored on cancellation"}
                </span>
              }
            />
            <InfoRow
              label={`Used in ${month}`}
              value={formatHours(b.approved_hours)}
            />
            <InfoRow label="Remaining" value={formatHours(b.remaining_hours)} />
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ── review actions ──────────────────────────────────────────────────────────

/** Approve / Reject with the same inline optional-note form the PM queue uses,
 *  so a decision made here and one made there are the same interaction.
 *
 *  `onDone` is what returns the reviewer to the queue they came from. This panel
 *  does not know or choose that destination; the page passes the href it already
 *  resolved from `?from`, so Permission requests -> Approve -> Permission
 *  requests follows from the SAME parameter the back link uses. Exactly how
 *  `leave-detail.tsx::ReviewPanel` has always worked. */
function ReviewActions({ id, onDone }: { id: string; onDone: () => void }) {
  const approve = useApprovePermission();
  const reject = useRejectPermission();
  const [action, setAction] = React.useState<"approve" | "reject" | null>(null);
  const [comment, setComment] = React.useState("");
  const busy = approve.isPending || reject.isPending;

  async function confirm() {
    if (!action) return;
    try {
      if (action === "approve") {
        await approve.mutateAsync({ id, body: { comment: comment || null } });
        toast.success("Permission request approved");
      } else {
        await reject.mutateAsync({ id, body: { comment: comment || null } });
        toast.success("Permission request rejected");
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

// ── cancellation review ─────────────────────────────────────────────────────

/** Approve / reject a withdrawal an employee has asked for.
 *
 *  Deliberately no comment box: neither `/approve-cancellation` nor
 *  `/reject-cancellation` takes one - the leave cancellation queue's two buttons
 *  don't either - so offering a field the API would discard would be a lie. */
function CancellationReviewActions({
  detail,
  onDone,
}: {
  detail: Detail;
  onDone: () => void;
}) {
  const approve = useApprovePermissionCancellation();
  const reject = useRejectPermissionCancellation();
  const busy = approve.isPending || reject.isPending;

  async function decide(decision: "approve" | "reject") {
    try {
      if (decision === "approve") {
        await approve.mutateAsync(detail.id);
        toast.success(
          "Cancellation approved. The permission is withdrawn and its hours are back.",
        );
      } else {
        await reject.mutateAsync(detail.id);
        toast.success("Cancellation rejected. The approved permission remains active.");
      }
      onDone();
    } catch (err) {
      toast.error(
        err instanceof AppError
          ? err.message
          : "Could not update the cancellation request.",
      );
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Cancellation request</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          {detail.employee_name ?? "This employee"} has asked to withdraw this
          approved permission. It stays approved - and keeps using{" "}
          {formatHours(detail.balance.consumed_by_request)} of{" "}
          {formatMonthLabel(detail.balance.month)} - until you decide.
        </p>
        <div className="flex items-center gap-2">
          <Button
            variant="danger"
            onClick={() => void decide("approve")}
            loading={approve.isPending}
            disabled={busy}
          >
            <Check className="h-4 w-4" />
            Approve cancellation
          </Button>
          <Button
            variant="secondary"
            onClick={() => void decide("reject")}
            loading={reject.isPending}
            disabled={busy}
          >
            <X className="h-4 w-4" />
            Keep approved permission
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ── page ────────────────────────────────────────────────────────────────────

/** One permission request in full: who, when, how long, what was decided and
 *  what it cost the month's allowance.
 *
 *  Serves both readers off the SAME endpoint and the same authorisation - an
 *  employee sees only their own, a project manager sees any - so there is no
 *  separate PM detail page to keep in step. What differs is only which actions
 *  render, and the backend refuses each of them independently. */
export function PermissionDetail({ id }: { id: string }) {
  const router = useRouter();
  const { role, employeeId } = useAuth();
  const isManager = role === "project_manager";

  // Head-ness is not a role - it is per-project and comes from the report scope,
  // exactly as `leave-detail.tsx` decides the same question. Same fact, same
  // source, so a Head who opens a request from their own Permission requests
  // queue can act on it here too. The backend re-checks the routed project on
  // every decision (`_assert_can_review`), so this only decides what renders.
  const { data: scope } = useReportScope({ enabled: !isManager });
  const isProjectHead = !isManager && scope?.is_project_head === true;

  const query = usePermissionRequest(id);
  const cancel = useCancelPermission();
  const requestCancellation = useRequestPermissionCancellation();

  // The list that opened this page, as it looked at the time - so the back link
  // returns to the All Requests tab with its filters and page intact, or to the
  // employee's own Permission History, or to whichever list it actually came
  // from. A page reached cold (a notification, an email link, a bookmark)
  // carries no `from` and falls back to Permission History, which is exactly
  // what this link did before Phase 4F.
  const searchParams = useSearchParams();
  const backHref = permissionReturnHref(searchParams.get(PERMISSION_RETURN_PARAM));

  if (query.isLoading) {
    return (
      <>
        <Skeleton className="mb-6 h-10 w-64" />
        <div className="space-y-4">
          <Skeleton className="h-56" />
          <Skeleton className="h-32" />
        </div>
      </>
    );
  }

  if (query.isError || !query.data) {
    const notFound = query.error instanceof AppError && query.error.status === 404;
    const forbidden = query.error instanceof AppError && query.error.status === 403;
    return (
      <ErrorState
        title={
          notFound
            ? "Permission request not found"
            : forbidden
              ? "Not available"
              : "Couldn't load permission request"
        }
        message={
          notFound
            ? "This permission request may have been removed."
            : forbidden
              ? "You can only view your own permission requests."
              : "Please try again."
        }
        onRetry={notFound || forbidden ? undefined : () => void query.refetch()}
      />
    );
  }

  const detail = query.data;
  const empName = detail.employee_name ?? detail.employee_id.slice(0, 8);
  const isReviewer = isManager || isProjectHead;
  const showReview = canReviewPermission(detail, isReviewer, employeeId);
  const showCancel = canCancelPermission(detail, employeeId);
  const showRequestCancellation = canRequestPermissionCancellation(detail, employeeId);
  const showCancellationReview = canReviewPermissionCancellation(
    detail,
    isReviewer,
    employeeId,
  );
  const reviewed = detail.reviewed_at || detail.reviewer_name || detail.manager_comment;
  // WHO IS HOLDING IT, or WHO DECIDED IT - one row, never both, because only one
  // of the two questions has an answer at a time. See `permissionActorRow`.
  const actorRow = permissionActorRow(detail);
  // The back link names where it actually goes: Permission History is the
  // employee's own list, anything else here is the Attendance Leave tab that
  // hosts All Requests.
  const backLabel = backHref.startsWith(PERMISSION_HISTORY_PATH)
    ? "← Permission History"
    : "← Leave Requests";
  // Whether this reader has ANY action here. Drives the closing "nothing more to
  // do" line, which must not appear beside a card offering something.
  const hasAction =
    showReview || showCancel || showRequestCancellation || showCancellationReview;

  async function onCancel() {
    try {
      await cancel.mutateAsync(detail.id);
      toast.success("Permission request cancelled");
    } catch (err) {
      toast.error(
        err instanceof AppError ? err.message : "Could not cancel the request.",
      );
    }
  }

  async function onRequestCancellation() {
    try {
      await requestCancellation.mutateAsync(detail.id);
      toast.success(
        "Cancellation requested. The permission stays approved until a reviewer decides.",
      );
    } catch (err) {
      toast.error(
        err instanceof AppError
          ? err.message
          : "Could not request cancellation of this permission.",
      );
    }
  }

  return (
    <>
      <Link href={backHref} className="text-sm text-primary hover:underline">
        {backLabel}
      </Link>
      <PageHeader
        className="mt-2"
        title={empName}
        subtitle={`Permission - ${formatShortDate(detail.permission_date)}`}
        actions={<PermissionStatusBadge status={detail.status} />}
      />

      <div className="space-y-4">
        <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
          <Card>
            <CardHeader>
              <CardTitle>Permission Request</CardTitle>
            </CardHeader>
            <CardContent className="divide-y divide-border">
              <InfoRow label="Employee" value={empName} />
              <InfoRow label="Employee ID" value={detail.employee_code ?? "-"} />
              <InfoRow label="Date" value={formatShortDate(detail.permission_date)} />
              <InfoRow label="Duration" value={formatPermissionDuration(detail)} />
              <InfoRow
                label="Status"
                value={<PermissionStatusBadge status={detail.status} />}
              />
              {/* TWO DIFFERENT FACTS, ONE ROW AT A TIME.
                  "Routed to" is who is holding a still-pending request, derived
                  fresh from the routed project on every read. "Reviewed by" is
                  the person who actually clicked Approve or Reject, read from
                  the `manager_id` stamped at that moment - so a Head or PM
                  reassigned since the decision does not rewrite history, and a
                  pending request never borrows the routed name to look decided.
                  Neither is ever derived from the other. */}
              {actorRow ? (
                <InfoRow label={actorRow.label} value={actorRow.name} />
              ) : null}
              <InfoRow label="Requested" value={fmtDateTime(detail.created_at)} />
              {/* The review fields appear only once there is something to show,
                  so a pending request does not render a column of dashes. */}
              {reviewed ? (
                <>
                  <InfoRow label="Reviewed" value={fmtDateTime(detail.reviewed_at)} />
                  {/* The reviewer's NAME is the `actorRow` above for a decided
                      request. This row remains for the statuses that carry a
                      recorded reviewer but deliberately show no actor - a
                      cancelled or withdrawal-pending permission - where hiding
                      the recorded name entirely would lose what the row knows. */}
                  {!actorRow && detail.reviewer_name ? (
                    <InfoRow label="Approved by" value={detail.reviewer_name} />
                  ) : null}
                  {detail.manager_comment?.trim() ? (
                    <InfoRow label="Manager note" value={detail.manager_comment} />
                  ) : null}
                </>
              ) : null}
            </CardContent>
          </Card>

          <BalanceCard detail={detail} />
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Reason</CardTitle>
          </CardHeader>
          <CardContent>
            {detail.reason?.trim() ? (
              <p className="whitespace-pre-wrap text-sm">{detail.reason}</p>
            ) : (
              <p className="text-sm text-muted-foreground">No reason provided.</p>
            )}
          </CardContent>
        </Card>

        {showReview && (
          <ReviewActions
            id={detail.id}
            // Back to the queue this page was opened from - the SAME href the
            // back link uses, resolved from the same `?from`. Approving out of
            // Permission requests therefore lands back on Permission requests,
            // out of All Requests back on All Requests with its filters, and a
            // cold-opened page (a notification, an email link, a bookmark) falls
            // back to Permission History exactly as before. Nothing here names a
            // destination; `permissionReturnHref` is the only thing that does.
            onDone={() => router.push(backHref)}
          />
        )}

        {showCancellationReview && (
          <CancellationReviewActions
            detail={detail}
            onDone={() => void query.refetch()}
          />
        )}

        {showCancel && (
          <Card>
            <CardHeader>
              <CardTitle>Withdraw</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Cancelling withdraws this request before it is reviewed.
              </p>
              <Button
                variant="danger"
                onClick={() => void onCancel()}
                loading={cancel.isPending}
                disabled={cancel.isPending}
              >
                Cancel permission request
              </Button>
            </CardContent>
          </Card>
        )}

        {/* An APPROVED permission is a granted absence: the employee asks, and a
            reviewer decides. Same workflow, same wording, as approved leave. */}
        {showRequestCancellation && (
          <Card>
            <CardHeader>
              <CardTitle>Withdraw</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                This permission is approved, so withdrawing it needs a reviewer&apos;s
                decision. It stays approved - and keeps using its hours - until
                they rule on your request.
              </p>
              <Button
                variant="secondary"
                onClick={() => void onRequestCancellation()}
                loading={requestCancellation.isPending}
                disabled={requestCancellation.isPending}
              >
                Request cancellation
              </Button>
            </CardContent>
          </Card>
        )}

        {/* The employee's own view while a withdrawal is being decided: no
            action, but the page must not simply end without saying so. */}
        {!hasAction && detail.status === "cancellation_requested" && (
          <p className="text-sm text-muted-foreground">
            A cancellation request for this permission is waiting for a
            reviewer&apos;s decision.
          </p>
        )}

        {/* A settled request the reader can do nothing with still explains itself
            rather than just ending. */}
        {!hasAction &&
          detail.status !== "pending" &&
          detail.status !== "cancellation_requested" && (
            <p className="text-sm text-muted-foreground">
              This request is {detail.status} and no further action is available.
            </p>
          )}
      </div>
    </>
  );
}
