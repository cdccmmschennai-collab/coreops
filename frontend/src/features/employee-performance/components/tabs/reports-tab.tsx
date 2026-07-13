"use client";

import { useRouter } from "next/navigation";

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
import { StatusBadge } from "@/features/work-reports/components/status-badge";
import type { WorkReport } from "@/features/work-reports/types";

import { useEmployeeWeekReports } from "../../hooks";

/** Distinct project names from a report's task snapshots, collapsed for display. */
function projectLabel(report: WorkReport): string {
  const names = [...new Set(report.tasks.map((t) => t.project_name).filter(Boolean))];
  if (names.length === 0) return "—";
  if (names.length === 1) return names[0] as string;
  return `${names.length} projects`;
}

// Layer 3, tab 5 — this week's work-report history for the employee.
export function ReportsTab({ employeeId }: { employeeId: string }) {
  const router = useRouter();
  const { data, isLoading } = useEmployeeWeekReports(employeeId);
  const reports = data?.items ?? [];

  if (isLoading) return <Skeleton className="h-48 w-full" />;

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b border-border px-5 py-3.5">
        <CardTitle className="text-base">Reports this week</CardTitle>
      </CardHeader>
      {reports.length === 0 ? (
        <p className="px-3 py-8 text-center text-sm text-muted-foreground">
          No reports submitted this week.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead>Project</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {reports.map((r) => (
              <TableRow
                key={r.id}
                className="cursor-pointer"
                onClick={() => router.push(`/work-reports/${r.id}`)}
              >
                <TableCell className="font-medium tabular">{r.report_date}</TableCell>
                <TableCell className="text-sm text-muted-foreground">{projectLabel(r)}</TableCell>
                <TableCell>
                  <StatusBadge status={r.status} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Card>
  );
}
