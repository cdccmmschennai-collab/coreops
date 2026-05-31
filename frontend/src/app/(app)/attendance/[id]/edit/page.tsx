"use client";

import { useParams } from "next/navigation";

import { RequireCapability } from "@/components/auth/require-capability";
import { AttendanceEdit } from "@/features/attendance/components/attendance-edit";

export default function EditAttendancePage() {
  const { id } = useParams<{ id: string }>();
  return (
    <RequireCapability capability="attendance.manage">
      <AttendanceEdit id={id} />
    </RequireCapability>
  );
}
