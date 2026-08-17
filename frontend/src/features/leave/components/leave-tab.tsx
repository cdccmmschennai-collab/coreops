"use client";

import { useAuth } from "@/features/auth/auth-provider";

import { LeaveHistory } from "./leave-history";
import { LeaveManagementPanel } from "./leave-management-panel";

/** Role-aware Leave tab content embedded inside the Attendance page.
 *
 *  Employees see their own leave history. Project managers get the queue
 *  container - which holds the permission review queue as one of its inner
 *  queues; the `queue` URL parameter only ever reaches that branch, so an
 *  employee cannot open a PM queue by editing the URL.
 *
 *  PERMISSION HISTORY IS NOT HERE. It moved to /attendance/permission (Phase
 *  11A), reached by clicking the Permission Remaining KPI card. That gives it
 *  month navigation and a URL that survives opening a request and pressing Back,
 *  neither of which a table wedged under a tab labelled "Leave" could have - and
 *  it means project managers can see their OWN permission history too, which they
 *  could not when it lived on the employee branch of this component. */
export function LeaveTab() {
  const { role, employeeId } = useAuth();

  if (role === "project_manager") {
    return <LeaveManagementPanel employeeId={employeeId ?? undefined} />;
  }

  return <LeaveHistory employeeId={employeeId ?? undefined} />;
}
