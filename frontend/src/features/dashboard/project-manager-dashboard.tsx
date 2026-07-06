"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight, CalendarOff, ClipboardList, ListPlus } from "lucide-react";

import { PageHeader } from "@/components/shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth/auth-provider";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { PerformanceTable } from "@/features/employee-performance/components/performance-table";
import { useActivityRequestPendingCount } from "@/features/activity-requests/hooks";
import { useLeaveList } from "@/features/leave/hooks";
import { useAllDeliverables } from "@/features/project-deliverables/hooks";
import { DeliverableStatusBadge } from "@/features/project-deliverables/components/status-badge";
import type { Deliverable } from "@/features/project-deliverables/types";

import { greeting } from "./utils";

// Active work (planned) first, completed last.
const STATUS_ORDER: Record<Deliverable["status"], number> = {
  planned: 0,
  completed: 1,
};

/**
 * PM dashboard — a manager summary built around the Employee Performance
 * comparison table, plus a Deliverables overview and quick shortcuts
 * (mirrors the employee dashboard's projects + quick-actions layout).
 */
export function ProjectManagerDashboard() {
  const { user, employeeId } = useAuth();
  const { items: employeeOptions } = useEmployeeOptions();

  const employee = employeeId
    ? employeeOptions.find((e) => e.id === employeeId)
    : undefined;
  const displayName =
    employee?.full_name?.trim() || user?.email.split("@")[0] || "there";

  const deliverablesQuery = useAllDeliverables();

  // Pending leave requests awaiting review — total drives the shortcut badge.
  const pendingLeave = useLeaveList({ status: "pending", limit: 1, offset: 0 });
  const pendingLeaveCount = pendingLeave.data?.total ?? 0;

  // Pending activity requests awaiting the PM's decision — drives the card badge.
  const activityRequestCount = useActivityRequestPendingCount();
  const pendingActivityRequests = activityRequestCount.data?.count ?? 0;

  // Active deliverables first, then by nearest planned submission date.
  const deliverables = React.useMemo(
    () =>
      [...(deliverablesQuery.data ?? [])]
        .sort((a, b) => {
          const byStatus = STATUS_ORDER[a.status] - STATUS_ORDER[b.status];
          if (byStatus !== 0) return byStatus;
          return (a.target_date ?? "9999").localeCompare(b.target_date ?? "9999");
        })
        .slice(0, 6),
    [deliverablesQuery.data],
  );

  return (
    <>
      <PageHeader
        title={`${greeting()}, ${displayName}`}
        subtitle={`${new Date().toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })} · Team overview`}
      />

      {/* Employee Performance — the primary dashboard section.
          Row click → /dashboard/employees/{id} for all per-employee detail. */}
      <PerformanceTable />

      {/* Deliverables + shortcuts (mirrors the employee dashboard layout). */}
      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        {/* deliverables overview */}
        <Card className="overflow-hidden">
          <CardHeader className="flex-row items-center justify-between space-y-0 border-b border-border px-5 py-3.5">
            <CardTitle className="text-base">Deliverables</CardTitle>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/projects/deliverables">
                View all <ArrowRight className="ml-1 h-3 w-3" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent className="p-2">
            {deliverablesQuery.isLoading ? (
              <div className="space-y-1 p-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-8 w-full" />
                ))}
              </div>
            ) : (
              deliverables.map((d) => (
                <Link
                  key={d.id}
                  href={`/projects/deliverables/${d.id}`}
                  className="flex items-center gap-3 rounded-md px-2.5 py-2.5 text-sm text-foreground transition-colors hover:bg-secondary"
                >
                  <span className="min-w-0 flex-1 truncate" title={d.name}>
                    {d.name}
                  </span>
                  {d.project_code && (
                    <span className="shrink-0 font-mono text-xs text-muted-foreground">
                      {d.project_code}
                    </span>
                  )}
                  <span className="shrink-0 tabular text-xs text-muted-foreground">
                    {d.target_date ?? "—"}
                  </span>
                  <DeliverableStatusBadge status={d.status} />
                </Link>
              ))
            )}
            {!deliverablesQuery.isLoading && deliverables.length === 0 && (
              <p className="px-3 py-4 text-sm text-muted-foreground">
                No deliverables yet.
              </p>
            )}
          </CardContent>
        </Card>

        {/* right column: activity requests + shortcuts */}
        <div className="flex flex-col gap-4">
        {/* activity requests */}
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0 border-b border-border px-5 py-3.5">
            <CardTitle className="text-base">Activity Requests</CardTitle>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/activity-requests">
                View all <ArrowRight className="ml-1 h-3 w-3" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent className="p-4">
            <Button asChild className="w-full justify-start" variant="secondary">
              <Link href="/activity-requests">
                <ListPlus className="h-4 w-4" /> Pending requests
                {pendingActivityRequests > 0 && (
                  <Badge variant="warning" className="ml-auto">
                    {pendingActivityRequests}
                  </Badge>
                )}
              </Link>
            </Button>
          </CardContent>
        </Card>

        {/* shortcuts */}
        <Card>
          <CardHeader className="border-b border-border px-5 py-3.5">
            <CardTitle className="text-base">Shortcuts</CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            <div className="flex flex-col gap-2">
              <Button asChild className="justify-start" variant="secondary">
                <Link href="/attendance?tab=leave">
                  <CalendarOff className="h-4 w-4" /> Leave requests
                  {pendingLeaveCount > 0 && (
                    <Badge variant="warning" className="ml-auto">
                      {pendingLeaveCount}
                    </Badge>
                  )}
                </Link>
              </Button>
              <Button asChild className="justify-start" variant="secondary">
                <Link href="/attendance/new">
                  <ClipboardList className="h-4 w-4" /> Record attendance
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>
        </div>
      </div>
    </>
  );
}
