"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, Pencil, Send, Trash2, X } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { useAuth } from "@/features/auth/auth-provider";
import { AppError } from "@/lib/api-client";
import { formatDateTime, formatMinutes } from "@/lib/format";
import { can } from "@/lib/rbac";

import { DeleteDialog } from "./delete-dialog";
import { RejectDialog } from "./reject-dialog";
import { StatusBadge } from "./status-badge";
import { useApproveWorkReport, useSubmitWorkReport, useWorkReport } from "../hooks";
import { useProjectOptions } from "../project-options";
import { DAY_STATUS_LABEL, WORK_LOCATION_LABEL, type DayStatus, type WorkLocation } from "../schemas";
import type { WorkReport } from "../types";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value ?? "—"}</span>
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
  const approve = useApproveWorkReport(id);
  const [rejectOpen, setRejectOpen] = React.useState(false);
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

  const employeeName = empById.get(report.employee_id) ?? "Employee";
  const isAuthor = !!employeeId && report.employee_id === employeeId;
  const isEditable = report.status === "draft" || report.status === "rejected";
  const canAuthorAct = isAuthor && can(role, "report.submit");
  const canReview = !isAuthor && report.status === "submitted" && can(role, "report.review");

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
      toast.success("Report submitted for review");
    } catch (error) {
      toast.error(error instanceof AppError ? error.message : "Could not submit report.");
    }
  }

  async function onApprove() {
    try {
      await approve.mutateAsync();
      toast.success("Report approved");
    } catch (error) {
      toast.error(error instanceof AppError ? error.message : "Could not approve report.");
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
      {canReview && (
        <>
          <Button onClick={() => void onApprove()} loading={approve.isPending}>
            <Check className="h-4 w-4" />
            Approve
          </Button>
          <Button variant="danger" onClick={() => setRejectOpen(true)}>
            <X className="h-4 w-4" />
            Reject
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

      {report.status === "rejected" && report.review_note && (
        <div
          role="alert"
          className="mb-4 max-w-2xl rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          <span className="font-medium">Rejected:</span> {report.review_note}
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
            {(report.status === "approved" || report.status === "rejected") && (
              <Row label="Reviewed" value={formatDateTime(report.reviewed_at)} />
            )}
          </CardContent>
        </Card>

        <div className="space-y-6">
          {/* Maintenance counters (shown if any > 0) */}
          {hasCounters && (
            <Card>
              <CardHeader>
                <CardTitle>Maintenance counts</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-x-8 gap-y-1">
                  <Row label="Task List" value={report.task_list_count ?? 0} />
                  <Row label="Task List Ops" value={report.task_list_op_count ?? 0} />
                  <Row label="Maint. Items" value={report.maintenance_item_count ?? 0} />
                  <Row label="Maint. Plans" value={report.maintenance_plan_count ?? 0} />
                </div>
              </CardContent>
            </Card>
          )}

          {/* Remarks (new field) */}
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

          {/* Activities table */}
          <Card>
            <CardHeader>
              <CardTitle>Project activities</CardTitle>
            </CardHeader>
            <CardContent className="px-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Project</TableHead>
                    <TableHead>Activity</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead className="text-right">Tags</TableHead>
                    <TableHead className="text-right">Docs</TableHead>
                    <TableHead className="text-right">BOM</TableHead>
                    <TableHead className="text-right">Spares</TableHead>
                    <TableHead className="text-right">Time</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {report.tasks.map((t) => (
                    <TableRow key={t.id}>
                      <TableCell className="font-medium">
                        {projById.get(t.project_id) ?? "—"}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {t.activity_type ?? "—"}
                      </TableCell>
                      <TableCell className="whitespace-pre-wrap text-muted-foreground">
                        {t.description}
                      </TableCell>
                      <TableCell className="text-right tabular">{t.tags_count ?? 0}</TableCell>
                      <TableCell className="text-right tabular">{t.docs_count ?? 0}</TableCell>
                      <TableCell className="text-right tabular">{t.bom_count ?? 0}</TableCell>
                      <TableCell className="text-right tabular">{t.spares_count ?? 0}</TableCell>
                      <TableCell className="text-right tabular">
                        {t.minutes_spent != null ? formatMinutes(t.minutes_spent) : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>
      </div>

      <RejectDialog
        reportId={report.id}
        open={rejectOpen}
        onOpenChange={setRejectOpen}
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
