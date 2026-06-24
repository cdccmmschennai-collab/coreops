"use client";

import { Kpi, KpiGrid } from "@/components/ui/kpi";
import { useMyLeaveBalance } from "@/features/leave-balances/hooks";
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
  const absent = items.filter((r) => r.status === "absent").length;

  return (
    <KpiGrid>
      <Kpi label="Present this month" value={`${present}d`} />
      <Kpi label="Leave taken" value={`${leave}d`} />
      <Kpi label="Available Leave" value={`${available}d`} />
      <Kpi label="Absent" value={`${absent}d`} />
    </KpiGrid>
  );
}
