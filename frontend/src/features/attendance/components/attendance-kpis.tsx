"use client";

import { Kpi, KpiGrid } from "@/components/ui/kpi";
import { formatMinutes } from "@/lib/format";

import { useAttendanceList } from "../hooks";
import { monthRange } from "../month";

/** Current-month attendance KPIs for the signed-in user (real data). */
export function AttendanceKpis({ employeeId }: { employeeId: string }) {
  const now = new Date();
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

  const present = items.filter((r) => r.status === "present").length;
  const leave = items.filter((r) => r.status === "leave").length;
  const half = items.filter((r) => r.status === "half_day").length;
  const withHours = items.filter((r) => r.total_minutes > 0);
  const avg = withHours.length
    ? Math.round(withHours.reduce((s, r) => s + r.total_minutes, 0) / withHours.length)
    : 0;

  return (
    <KpiGrid>
      <Kpi label="Present this month" value={`${present}d`} />
      <Kpi label="Leave taken" value={`${leave}d`} />
      <Kpi label="Half days" value={`${half}d`} />
      <Kpi label="Avg hours / day" value={avg ? formatMinutes(avg) : "—"} />
    </KpiGrid>
  );
}
