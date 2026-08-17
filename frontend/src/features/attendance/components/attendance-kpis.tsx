"use client";

import { Kpi, KpiGrid } from "@/components/ui/kpi";
import { useMyLeaveBalance } from "@/features/leave-balances/hooks";
import { PermissionRemainingKpi } from "@/features/permissions/components/permission-remaining-kpi";
import { nowInIST } from "@/lib/ist";

import { useAttendanceList } from "../hooks";
import { monthRange } from "../month";

/** Current-month attendance KPIs for the signed-in user (real data). */
export function AttendanceKpis({ employeeId }: { employeeId: string }) {
  const now = nowInIST();
  const { from, to } = monthRange(now.getFullYear(), now.getMonth());
  const query = useAttendanceList({
    employee_id: employeeId,
    status: "",
    from,
    to,
    limit: 100,
    offset: 0,
  });
  const items = query.data?.items ?? [];

  // Available Leave is the manager-maintained balance (source of truth), not
  // derived from attendance records.
  const balanceQuery = useMyLeaveBalance();
  const available = balanceQuery.data?.available_leave ?? 0;

  const present = items.filter((r) => r.status === "present").length;
  const leave = items.filter((r) => r.status === "leave").length;

  return (
    <KpiGrid>
      <Kpi label="Present this month" value={`${present}d`} />
      <Kpi label="Leave taken" value={`${leave}d`} />
      <Kpi label="Available Leave" value={`${available}d`} />
      {/* Replaces the former "Absent" tile (Phase 11). Absent days were a count
          of what went wrong; permission hours are something the employee acts
          on, which is why the Request entry point lives in this tile and nowhere
          else. It brings its own balance query - the current-month figure comes
          from the server, not from the attendance rows above. */}
      <PermissionRemainingKpi />
    </KpiGrid>
  );
}
