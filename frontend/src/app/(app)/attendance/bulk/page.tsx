"use client";

import { RequireCapability } from "@/components/auth/require-capability";
import { BulkAttendance } from "@/features/attendance/components/bulk-attendance";

export default function BulkAttendancePage() {
  return (
    <RequireCapability capability="attendance.manage">
      <BulkAttendance />
    </RequireCapability>
  );
}
