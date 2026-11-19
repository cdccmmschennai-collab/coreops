"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, ChevronLeft, X } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { AppError } from "@/lib/api-client";

import { useDecideReworkRequest, useReworkRequest } from "../hooks";
import {
  STATUS_LABEL,
  STATUS_TONE,
  canSubmitDecision,
  dayPartLabel,
  employeeLabel,
} from "../labels";
import type { ReworkRequest, ReworkRequestDetail } from "../types";
import { markReportOpenedFromList } from "@/features/work-reports/return-nav";

function formatDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0 space-y-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="break-words text-sm font-medium">{value || "-"}</dd>
    </div>
  );
}

const REWORK_LIST_PATH = "/activity-requests?tab=rework";

/**
 * Back always lands on the Rework Approvals list - never on whatever page
 * happened to open this one (the notifications panel, an email, the employee's
 * report). Opened FROM the list (?from=list), it steps back so the list's own
 * filters and page survive; from anywhere else it REPLACES this entry with the
 * list, so Back from the list can't bounce into this request again.
 */
function ReworkBackButton() {
  const router = useRouter();

  function handleClick() {
    const fromList =
      typeof window !== "undefined" &&
      new URLSearchParams(window.location.search).get("from") === "list" &&
      window.history.length > 1;
    if (fromList) router.back();
    else router.replace(REWORK_LIST_PATH);
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className="mb-3 inline-flex items-center gap-1 rounded text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ChevronLeft className="h-4 w-4" />
      Back to Rework Approvals
    </button>
  );
}

/** /activity-requests/rework/[id] - also the page the PM's email opens. */
export function ReworkApprovalDetail({ id }: { id: string }) {
  const query = useReworkRequest(id);

  return (
    <>
      <ReworkBackButton />
      {query.isLoading ? (
        <Card>
          <CardContent className="space-y-2 p-4">
            <Skeleton className="h-8 w-1/2" />
            <Skeleton className="h-24 w-full" />
          </CardContent>
        </Card>
      ) : query.isError || !query.data ? (
        <Card>
          <CardContent className="p-0">
            <ErrorState
              title={
                query.error instanceof AppError && query.error.status === 403
                  ? "You can't view this request"
                  : "Could not load the rework request"
              }
              message="Please go back and try again."
              onRetry={() => void query.refetch()}
            />
          </CardContent>
        </Card>
      ) : (
        <DetailBody req={query.data} />
      )}
    </>
  );
}

function DetailBody({ req }: { req: ReworkRequestDetail }) {
  return (
    <div className="space-y-4">
      <PageHeader
        title="Rework Approval Request"
        subtitle={`${employeeLabel(req.employee_code, req.employee_name)} | ${formatDate(req.report_date)}`}
        actions={
          <Badge variant={STATUS_TONE[req.status]} dot>
            {STATUS_LABEL[req.status]}
          </Badge>
        }
      />

      {/* Split: the info card (label | value rows, then the report's
          activities) on the left; PM Review + Approval History beside it.
          Stacks into one column on smaller screens. */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <Card className="h-fit">
        <CardContent className="p-5">
          <dl className="divide-y divide-border/60">
            <InfoRow
              label="Employee ID & Name"
              value={employeeLabel(req.employee_code, req.employee_name)}
            />
            {/* Project code only; the long name adds nothing for the review. */}
            <InfoRow label="Project" value={req.project_code || req.project_name} />
            <InfoRow label="Reporting Date" value={formatDate(req.report_date)} />
            <InfoRow label="Activity" value={req.activity_name} />
            <InfoRow label="Sub-Activity" value={req.sub_activity_name} />
            <InfoRow label="Day Part" value={dayPartLabel(req.day_part)} />
            <InfoRow
              label="Attempt"
              value={req.cycle_no > 1 ? `Resubmission ${req.cycle_no - 1}` : "First request"}
            />
            <InfoRow
              label="Remarks"
              value={
                req.employee_remarks?.trim() ? (
                  <span className="whitespace-pre-line">{req.employee_remarks}</span>
                ) : null
              }
            />
          </dl>

          {req.report_activities.length > 0 && (
            <div className="mt-5 border-t border-border pt-4">
              <div className="mb-2 flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold">Activities on this Report</h3>
                {req.report_id && (
                  <Button variant="ghost" size="sm" asChild>
                    <Link
                      href={`/work-reports/${req.report_id}`}
                      onClick={() => markReportOpenedFromList(req.report_id!)}
                    >
                      Open report
                    </Link>
                  </Button>
                )}
              </div>
              <ul className="divide-y divide-border/60">
                {req.report_activities.map((a, i) => (
                  <li key={i} className="flex items-start justify-between gap-3 py-2.5">
                    <div className="min-w-0">
                      <p className="text-sm font-medium">
                        {a.activity_name ?? "-"} / {a.sub_activity_name ?? "-"}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {a.project_code ?? "-"} | {dayPartLabel(a.day_part)}
                      </p>
                    </div>
                    <Badge
                      variant={a.rework_approval_status ? STATUS_TONE[a.rework_approval_status] : "neutral"}
                      className="shrink-0"
                    >
                      {a.rework_approval_status
                        ? STATUS_LABEL[a.rework_approval_status]
                        : "Submitted"}
                    </Badge>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="space-y-4">
        <ReviewPanel req={req} />
        <HistoryCard history={req.history} currentId={req.id} />
      </div>
      </div>
    </div>
  );
}

/** "Label    value" on one line (stacked on phones), as in the agreed layout. */
function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-0.5 py-2.5 sm:grid-cols-[11rem_minmax(0,1fr)] sm:gap-4">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="break-words text-sm font-medium">{value || "-"}</dd>
    </div>
  );
}

function ReviewPanel({ req }: { req: ReworkRequestDetail }) {
  const decide = useDecideReworkRequest(req.id);
  const [remarks, setRemarks] = React.useState("");
  const [acting, setActing] = React.useState<"approve" | "reject" | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  async function submit(kind: "approve" | "reject") {
    if (!canSubmitDecision(kind, remarks)) {
      setError("Rejection remarks are required.");
      return;
    }
    setError(null);
    setActing(kind);
    try {
      await decide.mutateAsync({ kind, remarks });
      toast.success(kind === "approve" ? "Rework approved" : "Rework rejected");
      setRemarks("");
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not save the decision.");
    } finally {
      setActing(null);
    }
  }

  if (req.status !== "pending") {
    return (
      <Card>
        <CardHeader className="border-b border-border px-5 py-3.5">
          <CardTitle className="text-base">PM Review</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-5">
          <dl className="space-y-3">
            <Field label="Decision" value={STATUS_LABEL[req.status]} />
            <Field label="Reviewed by" value={req.reviewer_name} />
            <Field label="Decided at" value={formatDateTime(req.decided_at)} />
            <Field label="PM Remarks" value={req.review_remarks} />
          </dl>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="border-b border-border px-5 py-3.5">
        <CardTitle className="text-base">PM Review</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-5">
        {!req.can_review ? (
          <p className="text-sm text-muted-foreground">
            {req.report_status && req.report_status !== "submitted"
              ? "The employee is editing this report. You can decide after they resubmit."
              : "Waiting for a Project Manager's decision."}
          </p>
        ) : (
          <>
            <div className="space-y-1">
              <label htmlFor="rework-remarks" className="text-xs text-muted-foreground">
                Remarks <span className="text-muted-foreground">(required to reject)</span>
              </label>
              <Textarea
                id="rework-remarks"
                value={remarks}
                onChange={(e) => {
                  setRemarks(e.target.value);
                  if (error) setError(null);
                }}
                rows={4}
                maxLength={2000}
                placeholder="Add a note for the employee..."
              />
              {error && <p className="text-xs text-destructive">{error}</p>}
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button
                className="flex-1"
                loading={acting === "approve"}
                disabled={acting !== null}
                onClick={() => void submit("approve")}
              >
                <Check className="h-4 w-4" />
                Approve
              </Button>
              <Button
                className="flex-1"
                variant="danger"
                loading={acting === "reject"}
                disabled={acting !== null}
                onClick={() => void submit("reject")}
              >
                <X className="h-4 w-4" />
                Reject
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function HistoryCard({ history, currentId }: { history: ReworkRequest[]; currentId: string }) {
  return (
    <Card>
      <CardHeader className="border-b border-border px-5 py-3.5">
        <CardTitle className="text-base">Approval History</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <ol className="divide-y divide-border">
          {[...history].reverse().map((h) => (
            <li key={h.id} className="space-y-1.5 px-5 py-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">
                  {h.cycle_no > 1 ? `Resubmission ${h.cycle_no - 1}` : "First request"}
                  {h.id === currentId && (
                    <span className="ml-1 text-xs text-muted-foreground">(this request)</span>
                  )}
                </span>
                <Badge variant={STATUS_TONE[h.status]} dot>
                  {STATUS_LABEL[h.status]}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground">
                Requested by {h.requested_by_name ?? "-"} on {formatDateTime(h.requested_at)}
              </p>
              {h.decided_at && (
                <p className="text-xs text-muted-foreground">
                  {STATUS_LABEL[h.status]} by {h.reviewer_name ?? "-"} on{" "}
                  {formatDateTime(h.decided_at)}
                </p>
              )}
              {h.review_remarks && (
                <p className="whitespace-pre-line rounded-md bg-muted/40 px-2 py-1 text-xs">
                  {h.review_remarks}
                </p>
              )}
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
