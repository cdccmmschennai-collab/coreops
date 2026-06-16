"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { KeyRound, Pencil, Send, Trash2, Undo2, Unlock } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { useAuth } from "@/features/auth/auth-provider";
import { AppError } from "@/lib/api-client";
import { formatDateTime, formatInt, formatMinutes } from "@/lib/format";
import { can } from "@/lib/rbac";

import { DeleteDialog } from "./delete-dialog";
import { RejectDialog } from "./reject-dialog";
import { RequestEditDialog } from "./request-edit-dialog";
import { StatusBadge } from "./status-badge";
import {
  useGrantEditWorkReport,
  useSubmitWorkReport,
  useToggleTaskCompletion,
  useWorkReport,
} from "../hooks";
import { useProjectOptions } from "../project-options";
import {
  DAY_STATUS_LABEL,
  WORK_LOCATION_LABEL,
  type DayStatus,
  type WorkLocation,
} from "../schemas";
import type { WorkReport, WorkReportTask } from "../types";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value ?? "—"}</span>
    </div>
  );
}

const COUNT_FIELD_LABEL: Record<string, string> = {
  tags: "Tags", docs: "Docs", bom: "BOM", spares: "Spares",
};

/** The NUMERIC benchmark's "actual" value — whichever of
 * tags_count/docs_count/bom_count/spares_count the sub-activity's
 * relevant_count_field named, frozen at submit time. There is no separate
 * actual-count field; this just reads the existing count straight off. */
function benchmarkActualCount(t: WorkReportTask): number | "—" {
  switch (t.relevant_count_field_snapshot) {
    case "tags":   return t.tags_count ?? 0;
    case "docs":   return t.docs_count ?? 0;
    case "bom":    return t.bom_count ?? 0;
    case "spares": return t.spares_count ?? 0;
    default:       return "—";
  }
}

/** Compact label-over-value cell used inside the activity cards. */
function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0 space-y-0.5">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="truncate text-sm font-medium tabular">{value ?? "—"}</p>
    </div>
  );
}

export function WorkReportDetail({ id }: { id: string }) {
  const router = useRouter();
  const { role, employeeId } = useAuth();

  const query = useWorkReport(id);
  const report = query.data;
  const { byId: empById } = useEmployeeOptions();
  const { byId: projById } = useProjectOptions();

  const submit = useSubmitWorkReport(id);
  const grantEdit = useGrantEditWorkReport(id);
  const toggleCompletion = useToggleTaskCompletion(id);
  const [rejectOpen, setRejectOpen] = React.useState(false);
  const [requestEditOpen, setRequestEditOpen] = React.useState(false);
  const [deleteTarget, setDeleteTarget] = React.useState<WorkReport | null>(null);

  if (query.isLoading) {
    return (
      <>
        <Skeleton className="mb-6 h-10 w-64" />
        <Skeleton className="h-56 max-w-2xl" />
      </>
    );
  }

  if (query.isError || !report) {
    const notFound = query.error instanceof AppError && query.error.status === 404;
    return (
      <ErrorState
        title={notFound ? "Report not found" : "Couldn't load report"}
        message={
          notFound
            ? "This report may have been deleted, or you don't have access to it."
            : "Please try again."
        }
        onRetry={notFound ? undefined : () => void query.refetch()}
      />
    );
  }

  const employeeName =
    report.employee_name ?? empById.get(report.employee_id) ?? "Employee";
  const isAuthor = !!employeeId && report.employee_id === employeeId;
  const isEditable =
    report.status === "draft" ||
    report.status === "rejected" ||
    report.status === "granted";
  const canAuthorAct = isAuthor && can(role, "report.submit");
  const isSubmitted = report.status === "submitted";
  const editRequested = !!report.edit_requested_at;
  // can_review is computed per-actor by the API (PM = any; team lead = their projects).
  const canReview = !isAuthor && report.can_review === true;

  const dayStatusLabel =
    report.day_status
      ? (DAY_STATUS_LABEL as Record<string, string>)[report.day_status] ?? report.day_status
      : null;

  const locationLabel =
    report.location
      ? (WORK_LOCATION_LABEL as Record<string, string>)[report.location] ?? report.location
      : null;

  const hasCounters =
    (report.task_list_count ?? 0) > 0 ||
    (report.task_list_op_count ?? 0) > 0 ||
    (report.maintenance_item_count ?? 0) > 0 ||
    (report.maintenance_plan_count ?? 0) > 0;

  async function onSubmit() {
    try {
      await submit.mutateAsync();
      toast.success("Report submitted");
    } catch (error) {
      toast.error(error instanceof AppError ? error.message : "Could not submit report.");
    }
  }

  async function onGrantEdit() {
    try {
      await grantEdit.mutateAsync();
      toast.success("Edit access granted");
    } catch (error) {
      toast.error(error instanceof AppError ? error.message : "Could not grant edit access.");
    }
  }

  // Works regardless of report.status — completing a TASK_BASED item often
  // happens days after the report it was logged on is already submitted.
  async function onToggleCompletion(taskId: string, next: boolean) {
    try {
      await toggleCompletion.mutateAsync({ taskId, isCompleted: next });
      toast.success(next ? "Marked complete" : "Marked incomplete");
    } catch (error) {
      toast.error(error instanceof AppError ? error.message : "Could not update completion.");
    }
  }

  const actions = (
    <>
      {canAuthorAct && isEditable && (
        <>
          <Button variant="secondary" asChild>
            <Link href={`/work-reports/${report.id}/edit`}>
              <Pencil className="h-4 w-4" />
              Edit
            </Link>
          </Button>
          <Button onClick={() => void onSubmit()} loading={submit.isPending}>
            <Send className="h-4 w-4" />
            Submit
          </Button>
        </>
      )}
      {canAuthorAct && report.status === "draft" && (
        <Button variant="danger" onClick={() => setDeleteTarget(report)}>
          <Trash2 className="h-4 w-4" />
          Delete
        </Button>
      )}
      {/* Author of a locked (submitted) report can request edit access */}
      {canAuthorAct && isSubmitted && !editRequested && (
        <Button variant="secondary" onClick={() => setRequestEditOpen(true)}>
          <KeyRound className="h-4 w-4" />
          Request edit
        </Button>
      )}
      {canAuthorAct && isSubmitted && editRequested && (
        <span className="rounded-md border border-border bg-muted/50 px-3 py-1.5 text-sm text-muted-foreground">
          Edit requested
        </span>
      )}
      {/* Reviewer (PM / team lead) actions on a submitted report.
          Grant edit only when the author has actually requested it. */}
      {canReview && isSubmitted && (
        <>
          {editRequested && (
            <Button onClick={() => void onGrantEdit()} loading={grantEdit.isPending}>
              <Unlock className="h-4 w-4" />
              Grant edit
            </Button>
          )}
          <Button variant="danger" onClick={() => setRejectOpen(true)}>
            <Undo2 className="h-4 w-4" />
            Send back
          </Button>
        </>
      )}
    </>
  );

  return (
    <>
      <Link href="/reports" className="text-sm text-primary hover:underline">
        ← Reports
      </Link>
      <PageHeader
        className="mt-2"
        title={`${employeeName} · ${report.report_date}`}
        actions={actions}
      />

      {/* Edit access granted — shown only to the author who requested it */}
      {report.status === "granted" && isAuthor && (
        <div className="mb-4 max-w-2xl rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-sm text-foreground">
          <span className="font-medium">Edit access granted.</span> You can edit and resubmit this report.
        </div>
      )}

      {/* Sent back for changes */}
      {report.status === "rejected" && report.review_note && (
        <div
          role="alert"
          className="mb-4 max-w-2xl rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          <span className="font-medium">Sent back:</span> {report.review_note}
        </div>
      )}

      {isSubmitted && editRequested && (
        <div className="mb-4 max-w-2xl rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-sm text-foreground">
          <span className="font-medium">Edit access requested.</span>{" "}
          {report.edit_request_note && <span>{report.edit_request_note}</span>}
          <span className="mt-1 block text-muted-foreground">
            {canReview
              ? "Grant edit to reopen the report, or send it back with a note."
              : "Waiting for a reviewer (PM or team lead) to respond."}
          </span>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,20rem)_1fr]">
        {/* Details card */}
        <Card>
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent className="divide-y divide-border">
            <Row label="Employee" value={employeeName} />
            <Row label="Date" value={report.report_date} />
            <Row label="Status" value={<StatusBadge status={report.status} />} />
            {dayStatusLabel && <Row label="Day Status" value={dayStatusLabel} />}
            {locationLabel && <Row label="Location" value={locationLabel} />}
            {report.well_head_no && <Row label="Well Head No." value={report.well_head_no} />}
            {report.pm_plant && <Row label="PM Plant" value={report.pm_plant} />}
            <Row label="Total" value={report.total_minutes > 0 ? formatMinutes(report.total_minutes) : "—"} />
            <Row label="Submitted" value={formatDateTime(report.submitted_at)} />
            {(report.status === "approved" ||
              report.status === "rejected" ||
              report.status === "granted") && (
              <Row label="Reviewed" value={formatDateTime(report.reviewed_at)} />
            )}
          </CardContent>
        </Card>

        <div className="space-y-6">
          {/* Project activities — one card per activity so wide data stays readable */}
          <Card>
            <CardHeader>
              <CardTitle>Project activities</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {report.tasks.length === 0 && (
                <p className="text-sm text-muted-foreground">No activities recorded.</p>
              )}
              {report.tasks.map((t) => {
                // Prefer snapshot fields (always current from migration 0017+).
                // Fall back to RBAC-scoped projById for pre-migration rows.
                const fallback = projById.get(t.project_id);
                const projectName = t.project_name ?? fallback?.name ?? "—";
                const projectCode = t.project_code ?? fallback?.code ?? "—";
                const jobCodeCode = t.project_job_code_code ?? fallback?.job_code_code ?? "—";
                return (
                  <div key={t.id} className="rounded-lg border border-border p-4">
                    {/* Header: project + duration */}
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <p className="font-medium leading-snug">{projectName}</p>
                        <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 font-mono text-xs text-muted-foreground">
                          <span>{projectCode}</span>
                          <span aria-hidden>·</span>
                          <span>{jobCodeCode}</span>
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="text-xs text-muted-foreground">Duration</p>
                        <p className="font-medium tabular">
                          {t.minutes_spent != null ? formatMinutes(t.minutes_spent) : "—"}
                        </p>
                      </div>
                    </div>

                    {/* Linked task (if any) + its hours */}
                    {t.task_title && (
                      <div className="mt-4 flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <p className="text-xs text-muted-foreground">Task</p>
                          <p className="text-sm font-medium">{t.task_title}</p>
                        </div>
                        <div className="shrink-0 text-right">
                          <p className="text-xs text-muted-foreground">Task hours</p>
                          <p className="text-sm font-medium tabular">
                            {t.task_minutes_spent != null ? formatMinutes(t.task_minutes_spent) : "—"}
                          </p>
                        </div>
                      </div>
                    )}

                    {/* Activity / Sub-Activity — new rows use the Activity Master;
                        legacy rows (filed before it existed) fall back to the old
                        free-text activity_type. */}
                    <div className="mt-4 space-y-0.5">
                      <p className="text-xs text-muted-foreground">
                        {t.sub_activity_id ? "Activity / Sub-Activity" : "Activity Type"}
                      </p>
                      <p className="text-sm font-medium">
                        {t.sub_activity_id
                          ? `${t.activity_name ?? "—"} / ${t.sub_activity_name ?? "—"}`
                          : t.activity_type ?? "—"}
                      </p>
                    </div>

                    {/* Benchmark — shape depends on the sub-activity's benchmark
                        type, frozen at submit time. Nothing renders for legacy
                        rows or sub-activities with no benchmark tracked. */}
                    {t.benchmark_type_snapshot === "NUMERIC" && (
                      <div className="mt-4 grid grid-cols-4 gap-x-6 gap-y-3 border-t border-border pt-3">
                        <Stat label="Target" value={formatInt(t.benchmark_value_snapshot)} />
                        <Stat
                          label={
                            t.relevant_count_field_snapshot
                              ? `Actual (${COUNT_FIELD_LABEL[t.relevant_count_field_snapshot] ?? t.relevant_count_field_snapshot})`
                              : "Actual"
                          }
                          value={benchmarkActualCount(t)}
                        />
                        <Stat label="Deficit" value={t.deficit ?? "—"} />
                        <Stat
                          label="Productivity %"
                          value={t.productivity_pct != null ? `${t.productivity_pct}%` : "—"}
                        />
                      </div>
                    )}
                    {/* TASK_BASED tracking — started_date/due_date are set as
                        soon as the row is saved (not gated on submit), so
                        this shows on drafts too; gate on started_date rather
                        than benchmark_type_snapshot (which is submit-only). */}
                    {t.started_date && (
                      <div className="mt-4 space-y-2 border-t border-border pt-3">
                        <div className="grid grid-cols-3 gap-x-6 gap-y-3">
                          <Stat label="Started" value={t.started_date} />
                          <Stat label="Due" value={t.due_date ?? "—"} />
                          <Stat label="Completed" value={t.completed_date ?? "—"} />
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          {t.is_completed ? (
                            <Badge variant="success">Completed</Badge>
                          ) : t.is_overdue ? (
                            <Badge variant="danger">Overdue by {t.days_overdue}d</Badge>
                          ) : (
                            <Badge variant="neutral">In progress</Badge>
                          )}
                          {isAuthor && (
                            <Button
                              type="button"
                              variant="secondary"
                              size="sm"
                              loading={toggleCompletion.isPending}
                              onClick={() => void onToggleCompletion(t.id, !t.is_completed)}
                            >
                              {t.is_completed ? "Reopen" : "Mark complete"}
                            </Button>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Counts — operational reporting, independent of the
                        benchmark above. */}
                    <div className="mt-4 grid grid-cols-4 gap-x-6 gap-y-3">
                      <Stat label="Tags" value={t.tags_count ?? 0} />
                      <Stat label="Docs" value={t.docs_count ?? 0} />
                      <Stat label="BOM" value={t.bom_count ?? 0} />
                      <Stat label="Spares" value={t.spares_count ?? 0} />
                    </div>

                    {/* Per-activity day remarks */}
                    {t.description && (
                      <div className="mt-4 border-t border-border pt-3">
                        <p className="text-xs text-muted-foreground">Day Remarks</p>
                        <p className="mt-1 whitespace-pre-wrap text-sm">{t.description}</p>
                      </div>
                    )}
                  </div>
                );
              })}
            </CardContent>
          </Card>

          {/* Day Remarks (report-level; present on older reports) */}
          {report.remarks && (
            <Card>
              <CardHeader>
                <CardTitle>Day Remarks</CardTitle>
              </CardHeader>
              <CardContent className="whitespace-pre-wrap text-sm text-muted-foreground">
                {report.remarks}
              </CardContent>
            </Card>
          )}

          {/* Legacy summary — shown only for old reports that have it */}
          {report.summary && !report.remarks && (
            <Card>
              <CardHeader>
                <CardTitle>Summary</CardTitle>
              </CardHeader>
              <CardContent className="whitespace-pre-wrap text-sm text-muted-foreground">
                {report.summary}
              </CardContent>
            </Card>
          )}

          {/* Query / Issues */}
          {report.query_text && (
            <Card>
              <CardHeader>
                <CardTitle>Query / Issues</CardTitle>
              </CardHeader>
              <CardContent className="whitespace-pre-wrap text-sm text-muted-foreground">
                {report.query_text}
              </CardContent>
            </Card>
          )}

          {/* Maintenance counts (shown if any > 0) */}
          {hasCounters && (
            <Card>
              <CardHeader>
                <CardTitle>Maintenance counts</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-x-8 gap-y-1 sm:grid-cols-4">
                  <Row label="Task List" value={report.task_list_count ?? 0} />
                  <Row label="Task List Ops" value={report.task_list_op_count ?? 0} />
                  <Row label="Maint. Items" value={report.maintenance_item_count ?? 0} />
                  <Row label="Maint. Plans" value={report.maintenance_plan_count ?? 0} />
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      <RejectDialog
        reportId={report.id}
        open={rejectOpen}
        onOpenChange={setRejectOpen}
      />
      <RequestEditDialog
        reportId={report.id}
        open={requestEditOpen}
        onOpenChange={setRequestEditOpen}
      />
      <DeleteDialog
        report={deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        onDone={() => router.push("/reports")}
      />
    </>
  );
}
