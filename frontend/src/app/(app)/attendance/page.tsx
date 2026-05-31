import { Suspense } from "react";

import { AttendanceView } from "@/features/attendance/components/attendance-view";

export default function AttendancePage() {
  return (
    <Suspense>
      <AttendanceView />
    </Suspense>
  );
}
