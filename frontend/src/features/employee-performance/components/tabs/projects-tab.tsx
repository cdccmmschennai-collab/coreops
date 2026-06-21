"use client";

import * as React from "react";

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
import { formatInt } from "@/lib/format";

import { useEmployeeWeekReports } from "../../hooks";

interface ProjectRow {
  key: string;
  name: string;
  code: string | null;
  days: number;
  activities: number;
  tags: number;
  docs: number;
  spares: number;
  bom: number;
}

interface ProjectAgg extends Omit<ProjectRow, "days"> {
  dates: Set<string>;
}

// Layer 3, tab 3 — this week's project contribution, aggregated from the
// employee's work-report tasks (days worked, activities, tags/docs/spares/bom).
export function ProjectsTab({ employeeId }: { employeeId: string }) {
  const { data, isLoading } = useEmployeeWeekReports(employeeId);

  const projects = React.useMemo<ProjectRow[]>(() => {
    const map = new Map<string, ProjectAgg>();
    for (const report of data?.items ?? []) {
      for (const t of report.tasks) {
        const key = t.project_id ?? t.project_name ?? "—";
        const row =
          map.get(key) ??
          {
            key,
            name: t.project_name ?? "—",
            code: t.project_code ?? null,
            dates: new Set<string>(),
            activities: 0,
            tags: 0,
            docs: 0,
            spares: 0,
            bom: 0,
          };
        // Distinct report dates = days the employee worked on this project.
        row.dates.add(report.report_date);
        row.activities += 1;
        row.tags += t.tags_count ?? 0;
        row.docs += t.docs_count ?? 0;
        row.spares += t.spares_count ?? 0;
        row.bom += t.bom_count ?? 0;
        map.set(key, row);
      }
    }
    return [...map.values()]
      .map(({ dates, ...r }) => ({ ...r, days: dates.size }))
      .sort((a, b) => b.days - a.days || b.activities - a.activities);
  }, [data]);

  if (isLoading) return <Skeleton className="h-48 w-full" />;

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b border-border px-5 py-3.5">
        <CardTitle className="text-base">
          Project contribution · {projects.length} project{projects.length === 1 ? "" : "s"} this week
        </CardTitle>
      </CardHeader>
      {projects.length === 0 ? (
        <p className="px-3 py-8 text-center text-sm text-muted-foreground">
          No project work logged this week.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Project</TableHead>
              <TableHead className="text-right">Days</TableHead>
              <TableHead className="text-right">Activities</TableHead>
              <TableHead className="text-right">Tags</TableHead>
              <TableHead className="text-right">Docs</TableHead>
              <TableHead className="text-right">Spares</TableHead>
              <TableHead className="text-right">BOM</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {projects.map((p) => (
              <TableRow key={p.key}>
                <TableCell className="font-bold tabular">{p.code ?? p.name}</TableCell>
                <TableCell className="tabular text-right">{formatInt(p.days)}</TableCell>
                <TableCell className="tabular text-right">{formatInt(p.activities)}</TableCell>
                <TableCell className="tabular text-right">{formatInt(p.tags)}</TableCell>
                <TableCell className="tabular text-right">{formatInt(p.docs)}</TableCell>
                <TableCell className="tabular text-right">{formatInt(p.spares)}</TableCell>
                <TableCell className="tabular text-right">{formatInt(p.bom)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Card>
  );
}
