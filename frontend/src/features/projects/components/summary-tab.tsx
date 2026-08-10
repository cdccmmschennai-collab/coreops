"use client";

import * as React from "react";
import { BarChart3, Search, TriangleAlert } from "lucide-react";

import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
import {
  OVER_REPORTED_HINT,
  OVER_REPORTED_LABEL,
  SUMMARY_NO_MATCH_HINT,
  SUMMARY_NO_MATCH_TITLE,
  SUMMARY_SEARCH_PLACEHOLDER,
  buildSummaryRows,
  filterSummaryRows,
  resolveSummaryState,
  summaryScopeCaption,
} from "../summary";

/**
 * Project Summary — progress against the project's tag scope.
 *
 * One row per tag-counted sub-activity actually reported on this project:
 * Activity, Sub-Activity, Reported / Scope, Remaining. Each row measures
 * against the SAME estimated tag count, because a project's tags are a universe
 * every scoped sub-activity works through independently — 700 / 1,200 on one
 * takes nothing away from another, and the rows are deliberately not shares of
 * a pool that add up to a project total.
 *
 * Visible to every user permitted to view the project. There is no
 * management-only interaction here: the tab shows one aggregate table and
 * nothing else. Employee-level and per-date records are a separate surface, not
 * an expansion of this one — a project with many activities, people and days
 * would make this page unusable if it tried to hold both.
 *
 * All of the logic lives in ../summary.ts so `node --test` can cover it; this
 * file only renders what that module decides.
 */
export function SummaryTab({ projectId }: { projectId: string }) {
  const query = useProjectSummary(projectId);
  const [search, setSearch] = React.useState("");

  const rows = React.useMemo(
    () => buildSummaryRows(query.data?.tag_progress),
    [query.data],
  );
  const visible = React.useMemo(() => filterSummaryRows(rows, search), [rows, search]);

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

  const state = resolveSummaryState(query.data);

  // Three genuinely different "nothing to show" situations, worded apart: a
  // normal project has no tag scope at all, a tag-based one is waiting on an
  // estimate, and a scoped one is waiting on its first report. None of them
  // invents a 0 / 0 row, and none lists every tags sub-activity in Activity
  // Master as 0 / 1,200 — the catalogue is not this project's plan of work.
  if (state.kind !== "table") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Summary</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState icon={BarChart3} title={state.title} description={state.description} />
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
        <div className="space-y-3 px-6 pb-4">
          <p className="text-sm text-muted-foreground">
            {summaryScopeCaption(query.data.estimated_tag_count)}
          </p>
          <div className="relative max-w-sm">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <Input
              type="search"
              className="pl-9"
              placeholder={SUMMARY_SEARCH_PLACEHOLDER}
              aria-label={SUMMARY_SEARCH_PLACEHOLDER}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        {visible.length === 0 ? (
          // Never a table with no body rows: an empty grid under a header reads
          // as a broken page rather than as "your search matched nothing".
          <EmptyState
            icon={Search}
            title={SUMMARY_NO_MATCH_TITLE}
            description={SUMMARY_NO_MATCH_HINT}
          />
        ) : (
          <>
            {/*
              Desktop table. The numeric columns are fixed-width and
              whitespace-nowrap so a long sub-activity name can never squeeze
              Reported or Remaining down to nothing or push them out of view;
              the name column absorbs the slack and wraps instead. `break-words`
              handles the FMTL descriptions, which run past 100 characters.
            */}
            {/* `Table` already supplies the overflow-x-auto wrapper; the
                min-width lives on the <table> so overflow becomes a visible
                scrollbar rather than crushed columns. */}
            <div className="hidden sm:block">
              <Table className="min-w-[42rem]">
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-40">Activity</TableHead>
                    <TableHead>Sub-Activity</TableHead>
                    <TableHead className="w-40 whitespace-nowrap text-right">
                      Reported / Scope
                    </TableHead>
                    <TableHead className="w-28 whitespace-nowrap text-right">
                      Remaining
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visible.map((r) => (
                    <TableRow key={r.key}>
                      <TableCell className="w-40 align-top font-medium">
                        {r.activityName}
                      </TableCell>
                      <TableCell className="align-top break-words text-muted-foreground">
                        {r.subActivityName}
                      </TableCell>
                      <TableCell className="w-40 whitespace-nowrap text-right align-top tabular">
                        {r.reportedOfScope}
                      </TableCell>
                      <TableCell className="w-28 whitespace-nowrap text-right align-top tabular font-medium">
                        {r.remaining}
                        {r.overReported && (
                          <Badge variant="warning" className="ml-2" title={OVER_REPORTED_HINT}>
                            <TriangleAlert className="h-3 w-3" aria-hidden />
                            {OVER_REPORTED_LABEL}
                          </Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {/*
              Narrow screens get cards instead of a table. A four-column grid
              holding a 100-character sub-activity name cannot be made readable
              on a phone by scrolling alone — and horizontal scroll is exactly
              how a Remaining figure ends up out of sight. Here every value has
              its own labelled line, so nothing depends on horizontal room.
            */}
            <ul className="divide-y divide-border border-t border-border sm:hidden">
              {visible.map((r) => (
                <li key={r.key} className="space-y-2 px-6 py-4">
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {r.activityName}
                    </div>
                    <div className="break-words text-sm font-medium">{r.subActivityName}</div>
                  </div>
                  <div className="flex items-center justify-between gap-4 text-sm">
                    <span className="text-muted-foreground">Reported / Scope</span>
                    <span className="tabular">{r.reportedOfScope}</span>
                  </div>
                  <div className="flex items-center justify-between gap-4 text-sm">
                    <span className="text-muted-foreground">Remaining</span>
                    <span className="tabular font-medium">{r.remaining}</span>
                  </div>
                  {r.overReported && (
                    <Badge variant="warning" title={OVER_REPORTED_HINT}>
                      <TriangleAlert className="h-3 w-3" aria-hidden />
                      {OVER_REPORTED_LABEL}
                    </Badge>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}
