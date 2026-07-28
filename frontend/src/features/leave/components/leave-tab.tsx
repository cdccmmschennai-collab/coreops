"use client";

import { useAuth } from "@/features/auth/auth-provider";

import { LeaveHistory } from "./leave-history";
import { LeaveManagementPanel } from "./leave-management-panel";

/** Role-aware Leave tab content embedded inside the Attendance page.
 *
 *  Employees see their own history. Project managers get the queue container —
 *  the `queue` URL parameter only ever reaches that branch, so an employee
 *  cannot open a PM queue by editing the URL. */
export function LeaveTab() {
  const { role, employeeId } = useAuth();

  if (role === "project_manager") {
    return <LeaveManagementPanel employeeId={employeeId ?? undefined} />;
  }

  return <LeaveHistory employeeId={employeeId ?? undefined} />;
}
