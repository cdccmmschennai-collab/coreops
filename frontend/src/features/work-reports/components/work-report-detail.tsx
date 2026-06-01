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
import type { WorkReport } from "../types";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
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
            ? "This work report may have been deleted, or you don't have access to it."
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
  const canReview =
    !isAuthor && report.status === "submitted" && can(role, "report.review");

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
      <Link href="/work-reports" className="text-sm text-primary hover:underline">
        ← Work Reports
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
        <Card>
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent className="divide-y divide-border">
            <Row label="Employee" value={employeeName} />
            <Row label="Date" value={report.report_date} />
            <Row label="Status" value={<StatusBadge status={report.status} />} />
            <Row label="Total" value={formatMinutes(report.total_minutes)} />
            <Row label="Submitted" value={formatDateTime(report.submitted_at)} />
            {(report.status === "approved" || report.status === "rejected") && (
              <Row label="Reviewed" value={formatDateTime(report.reviewed_at)} />
            )}
          </CardContent>
        </Card>

        <div className="space-y-6">
          {report.summary && (
            <Card>
              <CardHeader>
                <CardTitle>Summary</CardTitle>
              </CardHeader>
              <CardContent className="whitespace-pre-wrap text-sm text-muted-foreground">
                {report.summary}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Tasks</CardTitle>
            </CardHeader>
            <CardContent className="px-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Project</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead className="text-right">Time</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {report.tasks.map((t) => (
                    <TableRow key={t.id}>
                      <TableCell className="font-medium">
                        {projById.get(t.project_id) ?? "—"}
                      </TableCell>
                      <TableCell className="whitespace-pre-wrap text-muted-foreground">
                        {t.description}
                      </TableCell>
                      <TableCell className="text-right tabular">
                        {formatMinutes(t.minutes_spent)}
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
        onDone={() => router.push("/work-reports")}
      />
    </>
  );
}
