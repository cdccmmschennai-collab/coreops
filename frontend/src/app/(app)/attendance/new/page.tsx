"use client";

import Link from "next/link";

import { RequireCapability } from "@/components/auth/require-capability";
import { PageHeader } from "@/components/shell/page-header";
import { AttendanceSheet } from "@/features/attendance/components/attendance-sheet";

export default function NewAttendancePage() {
  return (
    <RequireCapability capability="attendance.manage">
      <Link href="/attendance" className="text-sm text-primary hover:underline">
        ← Attendance
      </Link>
      <PageHeader
        className="mt-2"
        title="Record attendance"
        subtitle="Record attendance for the whole team in one go."
      />
      <AttendanceSheet />
    </RequireCapability>
  );
}
