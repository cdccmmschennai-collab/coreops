"use client";

import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { RequireCapability } from "@/components/auth/require-capability";
import { PageHeader } from "@/components/shell/page-header";
import { parseReportDateParam } from "@/features/report-compliance/pending-target";
import { WorkReportForm } from "@/features/work-reports/components/work-report-form";
import { EMPTY_WORK_REPORT_FORM } from "@/features/work-reports/schemas";

/** Suspense boundary: `?date=` (set by "Submit Pending Reports") is read via
 *  `useSearchParams`. */
export default function NewWorkReportPage() {
  return (
    <RequireCapability capability="report.submit">
      <Link href="/reports" className="text-sm text-primary hover:underline">
        ← Reports
      </Link>
      <PageHeader
        className="mt-2"
        title="New report"
        subtitle="Log your project activities."
      />
      <React.Suspense fallback={null}>
        <NewWorkReportForm />
      </React.Suspense>
    </RequireCapability>
  );
}

/** Prefills ONLY the date, and only when it is a real `YYYY-MM-DD`; anything
 *  else opens the usual empty form. Everything else - Full Day default, the
 *  existing-report notice, server validation on save - is unchanged. */
function NewWorkReportForm() {
  const date = parseReportDateParam(useSearchParams().get("date"));
  return (
    <WorkReportForm
      // Keyed by date so a second "Submit Pending Reports" click that lands on
      // this same route re-initialises the form with the new date.
      key={date ?? ""}
      mode="create"
      defaultValues={date ? { ...EMPTY_WORK_REPORT_FORM, report_date: date } : EMPTY_WORK_REPORT_FORM}
    />
  );
}
