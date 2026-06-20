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
import { formatInt, formatMinutes } from "@/lib/format";

import { useEmployeeWeekReports } from "../../hooks";

interface ProjectRow {
  key: string;
  name: string;
  code: string | null;
  minutes: number;
  activities: number;
  tags: number;
  docs: number;
}

// Layer 3, tab 3 — this week's project contribution, aggregated from the
// employee's work-report tasks (hours, activities, tags, docs per project).
export function ProjectsTab({ employeeId }: { employeeId: string }) {
  const { data, isLoading } = useEmployeeWeekReports(employeeId);

  const projects = React.useMemo<ProjectRow[]>(() => {
    const map = new Map<string, ProjectRow>();
    for (const report of data?.items ?? []) {
      for (const t of report.tasks) {
        const key = t.project_id ?? t.project_name ?? "—";
        const row =
          map.get(key) ??
          { key, name: t.project_name ?? "—", code: t.project_code ?? null, minutes: 0, activities: 0, tags: 0, docs: 0 };
        row.minutes += t.minutes_spent ?? 0;
        row.activities += 1;
        row.tags += t.tags_count ?? 0;
        row.docs += t.docs_count ?? 0;
        map.set(key, row);
      }
    }
    return [...map.values()].sort((a, b) => b.minutes - a.minutes);
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
              <TableHead className="text-right">Hours</TableHead>
              <TableHead className="text-right">Activities</TableHead>
              <TableHead className="text-right">Tags</TableHead>
              <TableHead className="text-right">Docs</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {projects.map((p) => (
              <TableRow key={p.key}>
                <TableCell className="font-medium">
                  {p.name}
                  {p.code && <span className="ml-2 text-xs tabular text-muted-foreground">{p.code}</span>}
                </TableCell>
                <TableCell className="tabular text-right">{formatMinutes(p.minutes)}</TableCell>
                <TableCell className="tabular text-right">{formatInt(p.activities)}</TableCell>
                <TableCell className="tabular text-right">{formatInt(p.tags)}</TableCell>
                <TableCell className="tabular text-right">{formatInt(p.docs)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Card>
  );
}
