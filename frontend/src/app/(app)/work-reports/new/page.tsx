"use client";

import Link from "next/link";

import { RequireCapability } from "@/components/auth/require-capability";
import { PageHeader } from "@/components/shell/page-header";
import { WorkReportForm } from "@/features/work-reports/components/work-report-form";
import { EMPTY_WORK_REPORT_FORM } from "@/features/work-reports/schemas";

export default function NewWorkReportPage() {
  return (
    <RequireCapability capability="report.submit">
      <Link href="/work-reports" className="text-sm text-primary hover:underline">
        ← Work Reports
      </Link>
      <PageHeader
        className="mt-2"
        title="New work report"
        subtitle="Log what you worked on for a day."
      />
      <WorkReportForm mode="create" defaultValues={EMPTY_WORK_REPORT_FORM} />
    </RequireCapability>
  );
}
