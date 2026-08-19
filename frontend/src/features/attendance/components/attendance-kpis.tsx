"use client";

import * as React from "react";

import { Kpi, KpiGrid } from "@/components/ui/kpi";
import { useDailySummary } from "@/features/biometric/hooks";
import { useCalendarEvents } from "@/features/calendar/hooks";
import { useMyLeaveBalance } from "@/features/leave-balances/hooks";
import { PermissionRemainingKpi } from "@/features/permissions/components/permission-remaining-kpi";
import { nowInIST } from "@/lib/ist";

import { formatPresentDays, presentDaysInMonth } from "../day-status";
import { useAttendanceList } from "../hooks";
import { monthRange } from "../month";

/** Current-month attendance KPIs for the signed-in user (real data). */
export function AttendanceKpis({ employeeId }: { employeeId: string }) {
  const now = nowInIST();
  const year = now.getFullYear();
  const month = now.getMonth();
  const { from, to } = monthRange(year, month);
  const query = useAttendanceList({
    employee_id: employeeId,
    status: "",
    from,
    to,
    limit: 100,
    offset: 0,
  });
  const items = query.data?.items ?? [];

  // The other two inputs the calendar grid resolves a day from. Requested with
  // the SAME parameters the calendar uses, so on the Calendar tab these are the
  // very same cached queries rather than extra round trips.
  const eventsQuery = useCalendarEvents({ from, to, limit: 100 });
  const biometricQuery = useDailySummary({ employeeId, from, to });

  // Available Leave is the manager-maintained balance (source of truth), not
  // derived from attendance records.
  const balanceQuery = useMyLeaveBalance();
  const available = balanceQuery.data?.available_leave ?? 0;

  /**
   * Present days from the RESOLVED status of every date in the month, through
   * the same `day-status.ts` the calendar cell and the day popover use - not
   * from a count of `attendance_records` rows.
   *
   * That count was the bug: a day the device fully recorded showed as Present
   * on the calendar but added nothing here until a PM manually re-entered it.
   * A biometric present day is now worth 1.0 and an officially recorded half
   * day 0.5, and the card agrees with the grid it sits above.
   *
   * Nothing is written. This is arithmetic over data already fetched.
   */
  const present = React.useMemo(
    () =>
      presentDaysInMonth({
        year,
        month,
        records: query.data?.items ?? [],
        events: eventsQuery.data?.items ?? [],
        summaries: biometricQuery.data?.items ?? [],
      }),
    // The query results, not the `?? []` fallbacks above - those are a fresh
    // array on every render and would defeat the memo.
    [year, month, query.data, eventsQuery.data, biometricQuery.data],
  );

  // Untouched: leave taken is still the month's `leave` attendance records.
  const leave = items.filter((r) => r.status === "leave").length;

  return (
    <KpiGrid>
      <Kpi label="Present this month" value={`${formatPresentDays(present)}d`} />
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
