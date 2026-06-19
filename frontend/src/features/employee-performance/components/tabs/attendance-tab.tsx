"use client";

import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Kpi, KpiGrid } from "@/components/ui/kpi";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatusBadge } from "@/features/attendance/components/status-badge";
import { formatMinutes } from "@/lib/format";

import { useEmployeeWeekAttendance } from "../../hooks";

// Layer 3, tab 6 — this week's attendance (biometric-ready: when biometric
// capture lands it flows through the same attendance records shown here).
export function AttendanceTab({ employeeId }: { employeeId: string }) {
  const { data, isLoading } = useEmployeeWeekAttendance(employeeId);
  const items = data?.items ?? [];

  if (isLoading) return <Skeleton className="h-48 w-full" />;

  const presentDays = items.filter((a) => a.status === "present" || a.status === "half_day").length;
  const totalMinutes = items.reduce((sum, a) => sum + a.total_minutes, 0);

  return (
    <div className="space-y-4">
      <KpiGrid>
        <Kpi label="Days present" value={String(presentDays)} />
        <Kpi label="Hours this week" value={formatMinutes(totalMinutes)} />
        <Kpi label="Records" value={String(items.length)} />
      </KpiGrid>

      <Card className="overflow-hidden">
        <CardHeader className="border-b border-border px-5 py-3.5">
          <CardTitle className="text-base">Attendance this week</CardTitle>
        </CardHeader>
        {items.length === 0 ? (
          <p className="px-3 py-8 text-center text-sm text-muted-foreground">
            No attendance recorded this week.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Hours</TableHead>
                <TableHead className="text-right">Overtime</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="font-medium tabular">{a.attendance_date}</TableCell>
                  <TableCell>
                    <StatusBadge status={a.status} />
                  </TableCell>
                  <TableCell className="tabular text-right">{formatMinutes(a.total_minutes)}</TableCell>
                  <TableCell className="tabular text-right">
                    {a.overtime_minutes > 0 ? formatMinutes(a.overtime_minutes) : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
    </div>
  );
}
