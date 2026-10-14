"use client";

import Link from "next/link";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { AppError } from "@/lib/api-client";
import { toDatetimeLocal } from "@/lib/format";
import { istTodayISO } from "@/lib/ist";

import { AttendanceForm } from "./attendance-form";
import { initialReason } from "../date-rules";
import { useAttendance } from "../hooks";
import type { AttendanceFormValues } from "../schemas";

export function AttendanceEdit({ id }: { id: string }) {
  const query = useAttendance(id);
  const record = query.data;

  if (query.isLoading) {
    return (
      <>
        <Skeleton className="mb-6 h-10 w-64" />
        <Skeleton className="h-80" />
      </>
    );
  }

  if (query.isError || !record) {
    const notFound = query.error instanceof AppError && query.error.status === 404;
    return (
      <ErrorState
        title={notFound ? "Record not found" : "Couldn't load record"}
        message={notFound ? "This attendance record may have been deleted." : "Please try again."}
        onRetry={notFound ? undefined : () => void query.refetch()}
      />
    );
  }

  const defaults: AttendanceFormValues = {
    employee_id: record.employee_id,
    attendance_date: record.attendance_date,
    status: record.status,
    check_in_at: toDatetimeLocal(record.check_in_at),
    check_out_at: toDatetimeLocal(record.check_out_at),
    // Seeded like the Records dialog: empty for a past day (the correction
    // needs its own reason), the stored reason otherwise so a save keeps it.
    note: initialReason(record.attendance_date, record.note, istTodayISO()),
  };

  return (
    <>
      <Link href={`/attendance/${record.id}`} className="text-sm text-primary hover:underline">
        ← Attendance record
      </Link>
      <PageHeader
        className="mt-2"
        title="Edit attendance"
        subtitle={record.attendance_date}
      />
      <AttendanceForm mode="edit" recordId={record.id} defaultValues={defaults} />
    </>
  );
}
