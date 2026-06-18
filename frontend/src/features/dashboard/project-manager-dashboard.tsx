"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowRight,
  FileText,
  FolderKanban,
  Users,
  CalendarClock,
  ListChecks,
} from "lucide-react";

import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { useAuth } from "@/features/auth/auth-provider";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { useNotifications } from "@/features/notifications/hooks";
import { useProjects } from "@/features/projects/hooks";
import { StatusBadge } from "@/features/work-reports/components/status-badge";
import { useWorkReportList } from "@/features/work-reports/hooks";
import type { WorkReport } from "@/features/work-reports/types";
import { formatMinutes } from "@/lib/format";

import { greeting, timeAgo, todayISO, weekStartISO } from "./utils";

const MANAGER_ACTIONS = [
  { href: "/tasks/new", label: "Assign Task", icon: ListChecks },
  { href: "/reports", label: "View All Reports", icon: FileText },
  { href: "/projects", label: "Manage Projects", icon: FolderKanban },
  { href: "/employees", label: "Manage Employees", icon: Users },
  { href: "/attendance", label: "Attendance Overview", icon: CalendarClock },
];

/** Distinct project names from a report's task snapshots, collapsed for display. */
function projectLabel(report: WorkReport): string {
  const names = [...new Set(report.tasks.map((t) => t.project_name).filter(Boolean))];
  if (names.length === 0) return "—";
  if (names.length === 1) return names[0] as string;
  return `${names.length} projects`;
}

export function ProjectManagerDashboard() {
  const { user, employeeId } = useAuth();
  const { items: employeeOptions, byId: employeeById } = useEmployeeOptions();

  const employee = employeeId
    ? employeeOptions.find((e) => e.id === employeeId)
    : undefined;
  const displayName =
    employee?.full_name?.trim() || user?.email.split("@")[0] || "there";

  const today     = React.useMemo(todayISO, []);
  const weekStart = React.useMemo(weekStartISO, []);

  const nameOf = (id: string) => employeeById.get(id) ?? "Unknown employee";

  // Latest team submissions across all statuses (the PM work queue).
  const recent = useWorkReportList({
    employee_id: "", project_id: "", status: "",
    from: "", to: "", limit: 8, offset: 0,
  });

  // Submitted reports → filtered client-side for pending edit requests.
  const submittedReports = useWorkReportList({
    employee_id: "", project_id: "", status: "submitted",
    from: "", to: "", limit: 50, offset: 0,
  });

  // This week's reports → KPIs (counts + distinct authors).
  const weekReports = useWorkReportList({
    employee_id: "", project_id: "", status: "",
    from: weekStart, to: today, limit: 200, offset: 0,
  });

  const projects = useProjects({ q: "", status: "active", limit: 6, offset: 0 });
  const activity = useNotifications({ limit: 5 });

  // ── KPI computations ──────────────────────────────────────────────────────
  const weekItems        = weekReports.data?.items ?? [];
  const reportsThisWeek  = weekItems.length;
  const submittedThisWeek = weekItems.filter((r) => r.status !== "draft").length;
  const activeEmployees  = new Set(weekItems.map((r) => r.employee_id)).size;

  const editReqItems = (submittedReports.data?.items ?? []).filter((r) => r.edit_requested_at);
  const editReqCount = editReqItems.length;

  const recentItems = recent.data?.items ?? [];

  return (
    <>
      <PageHeader
        title={`${greeting()}, ${displayName}`}
        subtitle={`${new Date().toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })} · Team overview`}
      />

      {/* ── Team Overview KPIs ────────────────────────────────────────────── */}
      <KpiGrid>
        <Kpi label="Reports this week" value={String(reportsThisWeek)} />
        <Kpi label="Submitted this week" value={String(submittedThisWeek)} />
        <Kpi label="Edit requests" value={String(editReqCount)} />
        <Kpi label="Active employees" value={String(activeEmployees)} />
      </KpiGrid>

      {/* Pending edit requests — authors asking to reopen a locked report */}
      {editReqCount > 0 && (
        <Card className="overflow-hidden border-primary/40">
          <CardHeader className="flex-row items-center justify-between space-y-0 border-b border-border px-5 py-3.5">
            <CardTitle className="text-base">Edit requests</CardTitle>
            <span className="tabular rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">
              {editReqCount}
            </span>
          </CardHeader>
          <CardContent className="p-2">
            <ul className="divide-y divide-border">
              {editReqItems.map((r) => (
                <li key={r.id} className="flex items-center gap-2 px-2.5 py-2.5">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground">{nameOf(r.employee_id)}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {r.report_date} · requested {timeAgo(r.edit_requested_at)}
                    </p>
                  </div>
                  <Button size="sm" variant="secondary" asChild>
                    <Link href={`/work-reports/${r.id}`}>Review</Link>
                  </Button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* ── Recent Team Submissions | Active Projects ─────────────────────── */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        {/* Recent team submissions */}
        <Card className="overflow-hidden">
          <CardHeader className="flex-row items-center justify-between space-y-0 border-b border-border px-5 py-3.5">
            <CardTitle className="text-base">Recent team submissions</CardTitle>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/reports">View all <ArrowRight className="ml-1 h-3 w-3" /></Link>
            </Button>
          </CardHeader>
          {recent.isLoading ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Employee</TableHead>
                  <TableHead>Project</TableHead>
                  <TableHead>Hours</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recentItems.map((r) => (
                  <TableRow
                    key={r.id}
                    className="cursor-pointer"
                    onClick={() => window.location.assign(`/work-reports/${r.id}`)}
                  >
                    <TableCell className="font-medium tabular">{r.report_date}</TableCell>
                    <TableCell className="text-sm">{nameOf(r.employee_id)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{projectLabel(r)}</TableCell>
                    <TableCell className="tabular">{formatMinutes(r.total_minutes)}</TableCell>
                    <TableCell><StatusBadge status={r.status} /></TableCell>
                  </TableRow>
                ))}
                {recentItems.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                      No team submissions yet.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </Card>

        {/* Active projects */}
        <Card className="overflow-hidden">
          <CardHeader className="flex-row items-center justify-between space-y-0 border-b border-border px-5 py-3.5">
            <CardTitle className="text-base">Active projects</CardTitle>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/projects">View all <ArrowRight className="ml-1 h-3 w-3" /></Link>
            </Button>
          </CardHeader>
          <CardContent className="p-2">
            {projects.isLoading ? (
              <div className="space-y-2 p-2">
                {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
              </div>
            ) : (projects.data?.items ?? []).length === 0 ? (
              <p className="px-3 py-8 text-center text-sm text-muted-foreground">No active projects.</p>
            ) : (
              <ul className="divide-y divide-border">
                {(projects.data?.items ?? []).map((p) => (
                  <li key={p.id}>
                    <Link
                      href={`/projects/${p.id}`}
                      className="block rounded-md px-2.5 py-2.5 transition-colors hover:bg-secondary"
                    >
                      <p className="truncate text-sm font-medium text-foreground">{p.name}</p>
                      <p className="text-xs text-muted-foreground">
                        <span className="tabular">{p.code}</span>
                        {" · "}
                        {p.member_count} member{p.member_count === 1 ? "" : "s"}
                      </p>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Team Activity | Manager Actions ───────────────────────────────── */}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {/* Recent team activity */}
        <Card className="overflow-hidden">
          <CardHeader className="border-b border-border px-5 py-3.5">
            <CardTitle className="text-base">Recent team activity</CardTitle>
          </CardHeader>
          <CardContent className="p-2">
            {activity.isLoading ? (
              <div className="space-y-2 p-2">
                {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
              </div>
            ) : (activity.data?.items ?? []).length === 0 ? (
              <p className="px-3 py-8 text-center text-sm text-muted-foreground">No recent activity.</p>
            ) : (
              <ul className="divide-y divide-border">
                {(activity.data?.items ?? []).map((n) => {
                  const body = (
                    <>
                      <p className="text-sm text-foreground">{n.title}</p>
                      <p className="text-xs text-muted-foreground">{timeAgo(n.created_at)}</p>
                    </>
                  );
                  return (
                    <li key={n.id} className="px-2.5 py-2.5">
                      {n.target_url ? (
                        <Link href={n.target_url} className="block rounded-md transition-colors hover:bg-secondary">
                          {body}
                        </Link>
                      ) : (
                        body
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Manager actions */}
        <Card className="overflow-hidden">
          <CardHeader className="border-b border-border px-5 py-3.5">
            <CardTitle className="text-base">Manager actions</CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            <div className="flex flex-col gap-2">
              {MANAGER_ACTIONS.map(({ href, label, icon: Icon }) => (
                <Button key={href} asChild className="justify-start" variant="secondary">
                  <Link href={href}>
                    <Icon className="h-4 w-4" /> {label}
                  </Link>
                </Button>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
