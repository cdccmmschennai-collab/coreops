"use client";

import { Card, CardHeader, CardTitle } from "@/components/ui/card";
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

import { useEmployeeWeekAttendance } from "../../hooks";

const DOW = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

// Weekday name from a "YYYY-MM-DD" date, parsed as LOCAL so it can't drift a day.
function formatDay(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return DOW[new Date(y, m - 1, d).getDay()];
}

// Layer 3, tab 6 — this week's attendance (biometric-ready: when biometric
// capture lands it flows through the same attendance records shown here).
export function AttendanceTab({ employeeId }: { employeeId: string }) {
  const { data, isLoading } = useEmployeeWeekAttendance(employeeId);
  const items = data?.items ?? [];

  if (isLoading) return <Skeleton className="h-48 w-full" />;

  return (
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
              <TableHead>Day</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((a) => (
              <TableRow key={a.id}>
                <TableCell className="font-medium tabular">{a.attendance_date}</TableCell>
                <TableCell className="text-muted-foreground">{formatDay(a.attendance_date)}</TableCell>
                <TableCell>
                  <StatusBadge status={a.status} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Card>
  );
}
