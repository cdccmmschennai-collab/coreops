"use client";

import Link from "next/link";

import { RequireCapability } from "@/components/auth/require-capability";
import { PageHeader } from "@/components/shell/page-header";
import { AttendanceForm } from "@/features/attendance/components/attendance-form";
import { EMPTY_ATTENDANCE_FORM } from "@/features/attendance/schemas";

export default function NewAttendancePage() {
  return (
    <RequireCapability capability="attendance.manage">
      <Link href="/attendance" className="text-sm text-primary hover:underline">
        ← Attendance
      </Link>
      <PageHeader
        className="mt-2"
        title="Record attendance"
        subtitle="Add an attendance record for an employee."
      />
      <AttendanceForm mode="create" defaultValues={EMPTY_ATTENDANCE_FORM} />
    </RequireCapability>
  );
}
