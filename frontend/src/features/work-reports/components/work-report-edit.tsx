"use client";

import Link from "next/link";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth/auth-provider";
import { AppError } from "@/lib/api-client";

import { WorkReportForm } from "./work-report-form";
import { useWorkReport } from "../hooks";
import { toFormValues } from "../schemas";

export function WorkReportEdit({ id }: { id: string }) {
  const { employeeId } = useAuth();
  const query = useWorkReport(id);
  const report = query.data;

  if (query.isLoading) {
    return (
      <>
        <Skeleton className="mb-6 h-10 w-64" />
        <Skeleton className="h-80" />
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

  const isAuthor = !!employeeId && report.employee_id === employeeId;
  if (!isAuthor) {
    return (
      <ErrorState
        title="Not allowed"
        message="You can only edit your own reports."
      />
    );
  }

  // can_self_edit covers a Project Head editing their own submitted report
  // directly (backend allows the PATCH and reopens it to draft on save).
  const isEditable =
    report.status === "draft" ||
    report.status === "rejected" ||
    report.status === "granted" ||
    report.can_self_edit === true;
  if (!isEditable) {
    return (
      <ErrorState
        title="Report can't be edited"
        message="Only draft or rejected reports can be edited."
      />
    );
  }

  return (
    <>
      <Link
        href={`/work-reports/${report.id}`}
        className="text-sm text-primary hover:underline"
      >
        ← Report
      </Link>
      <PageHeader className="mt-2" title="Edit report" subtitle={report.report_date} />
      <WorkReportForm mode="edit" reportId={report.id} defaultValues={toFormValues(report)} />
    </>
  );
}
