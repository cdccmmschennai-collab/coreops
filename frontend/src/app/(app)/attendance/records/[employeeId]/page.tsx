"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { RequireCapability } from "@/components/auth/require-capability";
import { EmptyState } from "@/components/feedback/empty-state";
import { PageHeader } from "@/components/shell/page-header";

/**
 * Phase 9A stub: minimal routing structure only. Records rows navigate here
 * instead of opening the calendar-style popover; the full detail view -
 * biometric evidence, official record and edit history together - is
 * Phase 9B.
 */
function AttendanceRecordDetail() {
  const { employeeId } = useParams<{ employeeId: string }>();
  const searchParams = useSearchParams();
  const date = searchParams.get("date");

  return (
    <RequireCapability capability="attendance.manage">
      <Link
        href={date ? `/attendance?tab=history&date=${date}` : "/attendance?tab=history"}
        className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Records
      </Link>
      <PageHeader
        className="mt-2"
        title="Attendance detail"
        subtitle={date ? `Employee ${employeeId} · ${date}` : `Employee ${employeeId}`}
      />
      <EmptyState
        title="Coming in Phase 9B"
        description="The full daily attendance detail view - biometric evidence, official record and edit history side by side - is not built yet. Use the Records table to review and set this day for now."
      />
    </RequireCapability>
  );
}

export default function AttendanceRecordDetailPage() {
  return (
    <Suspense>
      <AttendanceRecordDetail />
    </Suspense>
  );
}
