"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { KeyRound, Pencil, Send, Trash2, Unlock } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMyActivityRequests } from "@/features/activity-requests/hooks";
import type { ActivityRequest } from "@/features/activity-requests/types";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { useAuth } from "@/features/auth/auth-provider";
import { AppError } from "@/lib/api-client";
import { formatDateTime, formatInt } from "@/lib/format";
import { can } from "@/lib/rbac";

import { DeleteDialog } from "./delete-dialog";
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
  pages: "Pages", records: "Records",
};

/** Every unit, paired with its count field — the read-side mirror of the
 *  backend's COUNT_FIELD_BY_UNIT. */
const COUNT_UNITS = [
  ["tags", "Tags"], ["docs", "Docs"], ["bom", "BOM"],
  ["spares", "Spares"], ["pages", "Pages"], ["records", "Records"],
] as const;

/** The benchmark modes that carry a numeric target/actual/deficit/productivity
 *  — the read-side mirror of the backend's QUANTITY_BENCHMARK_TYPES
 *  (activity_master/models.py). Legacy "NUMERIC" behaves identically to the
 *  current "NUMERIC_DAILY", so both must render the benchmark block. */
const QUANTITY_BENCHMARK_TYPES = new Set([
  "NUMERIC", "NUMERIC_DAILY", "TASK_WITH_QUANTITY",
]);

const countFor = (t: WorkReportTask, unit: string): number => {
  switch (unit) {
    case "tags":    return t.tags_count ?? 0;
    case "docs":    return t.docs_count ?? 0;
    case "bom":     return t.bom_count ?? 0;
    case "spares":  return t.spares_count ?? 0;
    case "pages":   return t.pages_count ?? 0;
    case "records": return t.records_count ?? 0;
    default:        return 0;
  }
};

// Task-continuation lifecycle (derived on the server from the work item's dates).
const LIFECYCLE_LABEL: Record<string, string> = {
  IN_PROGRESS: "In progress",
  DUE_TODAY: "Due today",
  OVERDUE: "Overdue",
  COMPLETED_ON_TIME: "Completed",
  COMPLETED_LATE: "Completed late",
};
const LIFECYCLE_VARIANT: Record<string, "neutral" | "warning" | "danger" | "success"> = {
  IN_PROGRESS: "neutral",
  DUE_TODAY: "warning",
  OVERDUE: "danger",
  COMPLETED_ON_TIME: "success",
  COMPLETED_LATE: "warning",
};

/** The NUMERIC benchmark's "actual" value — whichever of
 * tags_count/docs_count/bom_count/spares_count the sub-activity's
 * relevant_count_field named, frozen at submit time. There is no separate
 * actual-count field; this just reads the existing count straight off. */
function benchmarkActualCount(t: WorkReportTask): number | "—" {
  // Historical rows legitimately carry a legacy snapshot ('docs' etc.); it is
  // read as stored and never rewritten.
  if (!t.relevant_count_field_snapshot) return "—";
  return countFor(t, t.relevant_count_field_snapshot);
}

/** A second activity the author has requested but the PM hasn't decided yet.
 *  Rendered alongside the logged activities on the report info page so a
 *  requested activity is preserved and visibly marked as Pending / Rejected —
 *  on approval it becomes a normal activity row; on rejection it is not added. */
function RequestedActivityCard({ request }: { request: ActivityRequest }) {
  const isRejected = request.status === "rejected";
  return (
    <div className="rounded-lg border border-dashed border-border bg-muted/30 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium leading-snug">
            {request.project_name || request.project_code || "-"}
          </p>
          {request.project_code && (
            <p className="mt-1 font-mono text-xs text-muted-foreground">
              {request.project_code}
            </p>
          )}
        </div>
        <Badge variant={isRejected ? "danger" : "warning"}>
          {isRejected ? "Rejected" : "Pending PM Approval"}
        </Badge>
      </div>
      <div className="mt-4 space-y-0.5">
        <p className="text-xs text-muted-foreground">Activity / Sub-Activity</p>
        <p className="text-sm font-medium">
          {`${request.activity_name ?? "-"} / ${request.sub_activity_name || "-"}`}
        </p>
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        {isRejected
          ? "Your Project Manager declined this activity, so it was not added to the report. You can still submit the report."
          : "Waiting for your Project Manager to approve. Once approved it is added as an activity above."}
      </p>
    </div>
  );
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
  // Second activities the author has requested but the PM hasn't decided yet.
  // list_my_requests only returns pending/rejected (approved ones are already
  // real activity rows), and is author-scoped — enable only for the author.
  const viewerIsAuthor = !!employeeId && report?.employee_id === employeeId;
  const myRequests = useMyActivityRequests(id, viewerIsAuthor);
  const activityRequests = myRequests.data ?? [];
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
  // can_review is computed per-actor by the API — the Project Head of the
  // report's projects may grant edit access (never the PM).
  const canReview = !isAuthor && report.can_review === true;
  // can_self_edit is computed per-actor by the API — the author who is also the
  // current Project Head of one of this submitted report's projects may edit it
  // directly, skipping the request-edit/grant-edit handshake.
  const canSelfEdit = isAuthor && isSubmitted && report.can_self_edit === true;

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
      {/* Project Head editing their own submitted report: edit directly — no
          request-edit/grant-edit handshake (they're the report's only reviewer). */}
      {canAuthorAct && canSelfEdit && (
        <Button variant="secondary" asChild>
          <Link href={`/work-reports/${report.id}/edit`}>
            <Pencil className="h-4 w-4" />
            Edit
          </Link>
        </Button>
      )}
      {/* Author of a locked (submitted) report can request edit access — unless
          they're the Project Head, who edits directly (above). */}
      {canAuthorAct && isSubmitted && !editRequested && !canSelfEdit && (
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
      {/* Project Head action on a submitted report: grant edit access, only
          when the author has actually requested it. */}
      {canReview && isSubmitted && editRequested && (
        <Button onClick={() => void onGrantEdit()} loading={grantEdit.isPending}>
          <Unlock className="h-4 w-4" />
          Grant edit
        </Button>
      )}
    </>
  );

  return (
    <>
      {/* Go back to the list the user came from so their filters survive
          (router.back restores the previous URL, including its query string);
          fall back to a bare /reports only on a direct load with no history. */}
      <button
        type="button"
        onClick={() => (window.history.length > 1 ? router.back() : router.push("/reports"))}
        className="text-sm text-primary hover:underline"
      >
        ← Reports
      </button>
      <PageHeader
        className="mt-2"
        title={`${employeeName} · ${report.report_date}`}
        actions={actions}
      />

      {/* Activity-Lead partial view — the API trimmed this report's tasks to
          just the activities the viewer leads. */}
      {report.scoped_to_led_activities && (
        <div className="mb-4 max-w-2xl rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-sm text-foreground">
          <span className="font-medium">Partial view.</span> Only the activities
          you lead are shown; this report may contain other activities that are
          not visible to you.
        </div>
      )}

      {/* Edit access granted — shown only to the author who requested it */}
      {report.status === "granted" && isAuthor && (
        <div className="mb-4 max-w-2xl rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-sm text-foreground">
          <span className="font-medium">Edit access granted.</span> You can edit and resubmit this report.
        </div>
      )}

      {isSubmitted && editRequested && (
        <div className="mb-4 max-w-2xl rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-sm text-foreground">
          <span className="font-medium">Edit access requested.</span>{" "}
          {report.edit_request_note && <span>{report.edit_request_note}</span>}
          <span className="mt-1 block text-muted-foreground">
            {canReview
              ? "Grant edit to reopen the report for the author."
              : "Waiting for the Project Head to review your edit request."}
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
            <Row label="Status" value={<StatusBadge status={report.status} editRequested={editRequested} />} />
            {report.report_mode === "split_day" && (
              <Row label="Day Format" value="Split Day" />
            )}
            {dayStatusLabel && <Row label="Day Status" value={dayStatusLabel} />}
            {locationLabel && <Row label="Location" value={locationLabel} />}
            {report.well_head_no && <Row label="Well Head No." value={report.well_head_no} />}
            {report.pm_plant && <Row label="PM Plant" value={report.pm_plant} />}
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
              {/* Split Day: the review view leads with each half's status /
                  location / fraction / remarks; the activity cards below are
                  tagged with their half. A legacy half-day report (fraction
                  0.5 on a Full-Day period) is called out explicitly. */}
              {report.periods.length > 0 &&
                (report.report_mode === "split_day" ||
                  report.periods.some((p) => p.is_legacy_half_day)) && (
                <div className="grid gap-3 sm:grid-cols-2">
                  {report.periods.map((p) => (
                    <div
                      key={p.id}
                      className="rounded-lg border border-border bg-muted/30 p-3 text-sm"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold">
                          {p.day_part === "first_half"
                            ? "First Half"
                            : p.day_part === "second_half"
                              ? "Second Half"
                              : p.is_legacy_half_day
                                ? "Half Day (legacy)"
                                : "Full Day"}
                        </span>
                        {p.period_status && (
                          <Badge variant="neutral">
                            {(DAY_STATUS_LABEL as Record<string, string>)[p.period_status] ??
                              p.period_status}
                          </Badge>
                        )}
                        <span className="text-xs text-muted-foreground">
                          {Math.round(Number(p.work_fraction) * 100)}% of daily benchmark
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {p.location
                          ? (WORK_LOCATION_LABEL as Record<string, string>)[p.location] ??
                            p.location
                          : "No location"}
                        {" · "}
                        {p.tasks.length}{" "}
                        {p.tasks.length === 1 ? "activity" : "activities"}
                      </p>
                      {p.remarks && (
                        <p className="mt-1 whitespace-pre-wrap text-xs text-muted-foreground">
                          <span className="font-medium text-foreground">Remarks:</span>{" "}
                          {p.remarks}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {report.tasks.length === 0 && activityRequests.length === 0 && (
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
                    {/* Header: project (+ the half it belongs to on a split report) */}
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-medium leading-snug">{projectName}</p>
                        <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 font-mono text-xs text-muted-foreground">
                          <span>{projectCode}</span>
                          <span aria-hidden>·</span>
                          <span>{jobCodeCode}</span>
                        </p>
                      </div>
                      {report.report_mode === "split_day" && t.day_part && (
                        <Badge variant="neutral">
                          {t.day_part === "first_half" ? "First Half" : "Second Half"}
                        </Badge>
                      )}
                    </div>

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

                    {/* Maintenance Plant — independent of the project's own
                        assigned plant; which plant the employee worked at that day. */}
                    {t.maintenance_plant_id && (
                      <div className="mt-3 grid grid-cols-3 gap-x-6 gap-y-3">
                        <Stat label="Maintenance Plant" value={t.maintenance_plant_code ?? "—"} />
                        <Stat label="Planning Plant" value={t.planning_plant_code ?? "—"} />
                        <Stat label="Description (PP)" value={t.planning_plant_description ?? "—"} />
                      </div>
                    )}

                    {/* Benchmark — shape depends on the sub-activity's benchmark
                        type, frozen at submit time. Nothing renders for legacy
                        rows or sub-activities with no benchmark tracked. */}
                    {t.benchmark_type_snapshot &&
                      QUANTITY_BENCHMARK_TYPES.has(t.benchmark_type_snapshot) && (
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
                        <Stat label="Deficit" value={formatInt(t.deficit)} />
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
                      <div className="mt-4 space-y-3 border-t border-border pt-3">
                        <div className="grid grid-cols-3 gap-x-6 gap-y-3">
                          <Stat label="Started" value={t.started_date} />
                          <Stat label="Due" value={t.due_date ?? "—"} />
                          <Stat
                            label="Completed"
                            value={
                              t.work_item_id
                                ? t.overall_completed_on ?? "—"
                                : t.completed_date ?? "—"
                            }
                          />
                        </div>

                        {t.work_item_id ? (
                          /* Work-item row: keep the daily entry and the overall
                             task visibly separate — an earlier report of a task
                             completed later must not present an active checkbox. */
                          <>
                            <div className="space-y-0.5">
                              <p className="text-xs text-muted-foreground">Work on this report</p>
                              <p className="text-sm font-medium">
                                {t.completed_on_this_report
                                  ? `Completed on ${report.report_date}`
                                  : `Not completed on ${report.report_date}`}
                              </p>
                            </div>

                            <div className="flex items-end justify-between gap-3">
                              <div className="min-w-0 space-y-1">
                                <p className="text-xs text-muted-foreground">Overall task</p>
                                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                                  {t.overall_lifecycle && (
                                    <Badge variant={LIFECYCLE_VARIANT[t.overall_lifecycle] ?? "neutral"}>
                                      {t.overall_lifecycle === "OVERDUE" && t.days_overdue > 0
                                        ? `Overdue by ${t.days_overdue}d`
                                        : LIFECYCLE_LABEL[t.overall_lifecycle] ?? t.overall_lifecycle}
                                    </Badge>
                                  )}
                                  {t.overall_completed_on && !t.completed_on_this_report && (
                                    <span className="text-xs text-muted-foreground">
                                      Completed on {t.overall_completed_on}
                                      {t.completion_report_id && (
                                        <>
                                          {" · "}
                                          <Link
                                            href={`/work-reports/${t.completion_report_id}`}
                                            className="text-primary hover:underline"
                                          >
                                            View completion report
                                          </Link>
                                        </>
                                      )}
                                    </span>
                                  )}
                                </div>
                              </div>

                              {/* Completion control only where the server says it's
                                  valid (open task, editable report, latest linked
                                  entry). The completion row can be reopened while
                                  still editable; otherwise completion is read-only. */}
                              {isAuthor && t.can_complete_here === true && (
                                <Button
                                  type="button"
                                  variant="secondary"
                                  size="sm"
                                  loading={toggleCompletion.isPending}
                                  onClick={() => void onToggleCompletion(t.id, true)}
                                >
                                  {`Complete this overall task on ${report.report_date}`}
                                </Button>
                              )}
                              {isAuthor && t.completed_on_this_report && isEditable && (
                                <Button
                                  type="button"
                                  variant="secondary"
                                  size="sm"
                                  loading={toggleCompletion.isPending}
                                  onClick={() => void onToggleCompletion(t.id, false)}
                                >
                                  Reopen
                                </Button>
                              )}
                            </div>
                          </>
                        ) : (
                          /* Legacy standalone TASK_BASED row — unchanged. */
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
                        )}
                      </div>
                    )}

                    {/* Counts — operational reporting, independent of the
                        benchmark above. Only units that carry a value are shown,
                        plus the row's own benchmarked unit (even at zero, since
                        "0 pages today" is itself the reportable fact). Six
                        zero-valued units are never listed.

                        When the row has a quantity benchmark, its benchmarked
                        unit is already shown above as "Actual (…)", so it is
                        dropped here to avoid printing the same number twice. */}
                    {(() => {
                      const benchmarked = t.relevant_count_field_snapshot;
                      const hasQuantityBenchmark =
                        !!t.benchmark_type_snapshot &&
                        QUANTITY_BENCHMARK_TYPES.has(t.benchmark_type_snapshot);
                      const shown = COUNT_UNITS.filter(([unit]) => {
                        if (unit === benchmarked && hasQuantityBenchmark) return false;
                        return countFor(t, unit) > 0 || unit === benchmarked;
                      });
                      if (shown.length === 0) return null;
                      return (
                        <div className="mt-4 grid grid-cols-4 gap-x-6 gap-y-3">
                          {shown.map(([unit, label]) => (
                            <Stat key={unit} label={label} value={countFor(t, unit)} />
                          ))}
                        </div>
                      );
                    })()}

                    {/* Per-activity remarks */}
                    {t.description && (
                      <div className="mt-4 border-t border-border pt-3">
                        <p className="text-xs text-muted-foreground">Remarks</p>
                        <p className="mt-1 whitespace-pre-wrap text-sm">{t.description}</p>
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Requested second activities awaiting the PM. Shown to the author
                  so the requested activity is preserved and clearly marked until
                  it's approved (becomes a normal activity above) or rejected. */}
              {activityRequests.map((r) => (
                <RequestedActivityCard key={r.id} request={r} />
              ))}
            </CardContent>
          </Card>

          {/* Remarks (report-level, one per day) */}
          {report.remarks && (
            <Card>
              <CardHeader>
                <CardTitle>Remarks</CardTitle>
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
