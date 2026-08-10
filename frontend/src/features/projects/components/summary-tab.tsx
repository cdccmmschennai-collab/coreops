"use client";

import { BarChart3 } from "lucide-react";

import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { useProjectSummary } from "../hooks";
import { formatTagCount } from "../scope";

/**
 * Project Summary — progress against the project's tag scope.
 *
 * One row per tag-counted sub-activity actually reported on this project, each
 * measured against the SAME estimated tag count. The rows are deliberately not
 * a breakdown of a shared pool and do not sum to the project total: a project's
 * 2,500 tags are a universe every scoped activity works through independently,
 * so 1,000/2,500 on one activity takes nothing away from another.
 *
 * Visible to every user permitted to view the project.
 */
export function SummaryTab({ projectId }: { projectId: string }) {
  const query = useProjectSummary(projectId);

  if (query.isLoading) return <Skeleton className="h-64" />;

  if (query.isError || !query.data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Summary</CardTitle>
        </CardHeader>
        <CardContent>
          <ErrorState
            title="Couldn't load summary"
            message="Please try again."
            onRetry={() => void query.refetch()}
          />
        </CardContent>
      </Card>
    );
  }

  const summary = query.data;
  const rows = summary.tag_progress ?? [];

  // Two different "nothing to show" cases, deliberately worded apart: a normal
  // project will never have tag progress, whereas a tag-based one is simply
  // waiting on a scope or on its first report. Neither invents a 0 / 0.
  if (rows.length === 0) {
    const isTagBased = summary.scope_type === "TAG_BASED";
    const hasScope = summary.estimated_tag_count != null;
    return (
      <Card>
        <CardHeader>
          <CardTitle>Summary</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            icon={BarChart3}
            title="No tag progress yet"
            description={
              !isTagBased
                ? "This project is not tag-based, so there is no tag scope to report against."
                : !hasScope
                  ? "Set the project's estimated tag scope on the Tag Scope tab to start tracking progress."
                  : "No tag-counted work has been reported on this project yet."
            }
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Summary</CardTitle>
      </CardHeader>
      <CardContent className="px-0 pb-0">
        <p className="px-6 pb-3 text-sm text-muted-foreground">
          Each activity progresses through the project&apos;s{" "}
          <span className="font-medium text-foreground">
            {formatTagCount(summary.estimated_tag_count)}
          </span>{" "}
          tags independently.
        </p>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Sub-Activity</TableHead>
              <TableHead className="w-40 text-right">Reported</TableHead>
              <TableHead className="w-32 text-right">Remaining</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.sub_activity_id}>
                <TableCell className="font-medium">{r.sub_activity_name}</TableCell>
                <TableCell className="text-right tabular">
                  {formatTagCount(r.reported_tags)}{" "}
                  <span className="text-muted-foreground">
                    / {formatTagCount(r.estimated_tag_count)}
                  </span>
                </TableCell>
                <TableCell className="text-right tabular">
                  {formatTagCount(r.remaining_tags)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
