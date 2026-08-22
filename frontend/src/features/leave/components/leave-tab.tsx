"use client";

import { useAuth } from "@/features/auth/auth-provider";
import { useReportScope } from "@/features/work-reports/hooks";

import { HeadLeaveTab } from "./head-leave-tab";
import { LeaveHistory } from "./leave-history";
import { LeaveManagementPanel } from "./leave-management-panel";

/** Role-aware Leave tab content embedded inside the Attendance page.
 *
 *  Employees see their own leave history. Project managers get the queue
 *  container - which holds the permission review queue as one of its inner
 *  queues; the `queue` URL parameter only ever reaches that branch, so an
 *  employee cannot open a PM queue by editing the URL.
 *
 *  A Project Head (role stays "employee"; Head-ness is per-project, derived
 *  server-side from Project.head_employee_id - see
 *  `app.core.authz.reviewable_project_ids`, the same fact Work Reports already
 *  surfaces via `useReportScope`) gets BOTH their own history and a
 *  PM-equivalent approval view, via `HeadLeaveTab`.
 *
 *  PERMISSION HISTORY IS NOT HERE. It moved to /attendance/permission (Phase
 *  11A), reached by clicking the Permission Remaining KPI card. That gives it
 *  month navigation and a URL that survives opening a request and pressing Back,
 *  neither of which a table wedged under a tab labelled "Leave" could have - and
 *  it means project managers can see their OWN permission history too, which they
 *  could not when it lived on the employee branch of this component. */
export function LeaveTab() {
  const { role, employeeId } = useAuth();
  const { data: scope } = useReportScope({ enabled: role !== "project_manager" });
  const isProjectHead = role !== "project_manager" && scope?.is_project_head === true;

  if (role === "project_manager") {
    return <LeaveManagementPanel employeeId={employeeId ?? undefined} />;
  }

  if (isProjectHead) {
    return <HeadLeaveTab employeeId={employeeId ?? undefined} />;
  }

  return <LeaveHistory employeeId={employeeId ?? undefined} />;
}
