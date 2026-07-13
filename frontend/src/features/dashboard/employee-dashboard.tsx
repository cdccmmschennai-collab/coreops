"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, CalendarOff, FileText, Plus } from "lucide-react";

import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
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
import { useAuth } from "@/features/auth/auth-provider";
import { BenchmarkActivities } from "@/features/benchmarks/components/benchmark-activities";
import { useProjects } from "@/features/projects/hooks";
import { StatusBadge } from "@/features/work-reports/components/status-badge";
import { useWorkReportList } from "@/features/work-reports/hooks";
import { projectSummary } from "@/features/work-reports/project-summary";

import { greeting, todayISO, weekStartISO } from "./utils";

const CHART_COLORS = ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444", "#6366f1"];

// ── sub-components ────────────────────────────────────────────────────────────

function ProjectDot({ i }: { i: number }) {
  return (
    <span
      className="inline-block h-2 w-2 shrink-0 rounded-sm"
      style={{ background: CHART_COLORS[i % CHART_COLORS.length] }}
    />
  );
}

// ── main view ────────────────────────────────────────────────────────────────

export function EmployeeDashboard() {
  const router = useRouter();
  const { user, employee, employeeId } = useAuth();

  // Greet by employee full name — never the username/email/login id.
  // Resolution order: Employee.full_name (from /auth/me) → username fallback.
  const displayName =
    employee?.full_name?.trim() || user?.email.split("@")[0] || "there";
  const today     = React.useMemo(todayISO, []);
  const weekStart = React.useMemo(weekStartISO, []);

  // recent reports (own, latest 5)
  const recentReports = useWorkReportList({
    employee_id: employeeId ?? "",
    project_id: "",
    status: "",
    from: "",
    to: "",
    limit: 5,
    offset: 0,
  });

  // active projects (full-width section)
  const projects = useProjects({ q: "", status: "active", limit: 6, offset: 0 });

  // latest 5, sorted by report date descending
  const recentItems = React.useMemo(
    () =>
      [...(recentReports.data?.items ?? [])]
        .sort((a, b) => b.report_date.localeCompare(a.report_date))
        .slice(0, 5),
    [recentReports.data?.items],
  );

  return (
    <>
      <PageHeader
        title={`${greeting()}, ${displayName}`}
        subtitle={`${new Date().toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })} · ${weekStart === today ? "No reports due" : "Track your work below"}`}
        actions={
          <Button asChild>
            <Link href="/work-reports/new">
              <Plus className="h-4 w-4" />
              New report
            </Link>
          </Button>
        }
      />

      <BenchmarkActivities />

      {/* active projects — full width */}
      <Card className="overflow-hidden">
        <CardHeader className="border-b border-border px-5 py-3.5">
          <CardTitle className="text-base">Active projects</CardTitle>
        </CardHeader>
        <CardContent className="p-2">
          {projects.isLoading ? (
            <div className="space-y-1 p-2">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}
            </div>
          ) : (
            (projects.data?.items ?? []).map((p, i) => (
              <Link
                key={p.id}
                href={`/projects/${p.id}`}
                className="flex items-center gap-3 rounded-md px-2.5 py-2.5 text-sm text-foreground transition-colors hover:bg-secondary"
              >
                <ProjectDot i={i} />
                <span className="min-w-0 flex-1">{p.name}</span>
                <span className="tabular shrink-0 text-xs text-muted-foreground">{p.code}</span>
              </Link>
            ))
          )}
          {!projects.isLoading && (projects.data?.items ?? []).length === 0 && (
            <p className="px-3 py-4 text-sm text-muted-foreground">No active projects.</p>
          )}
        </CardContent>
      </Card>

      {/* recent reports + quick actions */}
      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        {/* recent reports (latest 5) */}
        <Card className="overflow-hidden">
          <CardHeader className="flex-row items-center justify-between space-y-0 border-b border-border px-5 py-3.5">
            <CardTitle className="text-base">Recent work reports</CardTitle>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/reports">View all <ArrowRight className="ml-1 h-3 w-3" /></Link>
            </Button>
          </CardHeader>
          {recentReports.isLoading ? (
            <div className="p-4 space-y-2">
              {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}
            </div>
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
                {recentItems.map((r) => {
                  const proj = projectSummary(r);
                  return (
                    <TableRow
                      key={r.id}
                      className="cursor-pointer"
                      onClick={() => router.push(`/work-reports/${r.id}`)}
                    >
                      <TableCell className="font-medium tabular">{r.report_date}</TableCell>
                      <TableCell
                        className="max-w-[320px] truncate text-sm text-muted-foreground"
                        title={proj.title}
                      >
                        {proj.label}
                      </TableCell>
                      <TableCell><StatusBadge status={r.status} /></TableCell>
                    </TableRow>
                  );
                })}
                {recentItems.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={3} className="py-8 text-center text-sm text-muted-foreground">
                      No work reports yet.{" "}
                      <Link href="/work-reports/new" className="text-primary hover:underline">
                        Create your first report
                      </Link>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </Card>

        {/* quick actions */}
        <Card>
          <CardHeader className="border-b border-border px-5 py-3.5">
            <CardTitle className="text-base">Quick actions</CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            <div className="flex flex-col gap-2">
              <Button asChild className="justify-start" variant="secondary">
                <Link href="/work-reports/new">
                  <Plus className="h-4 w-4" /> New work report
                </Link>
              </Button>
              <Button asChild className="justify-start" variant="secondary">
                <Link href="/attendance"><ArrowRight className="h-4 w-4" /> View attendance</Link>
              </Button>
              <Button asChild className="justify-start" variant="secondary">
                <Link href="/reports"><FileText className="h-4 w-4" /> All my reports</Link>
              </Button>
              <Button asChild className="justify-start" variant="secondary">
                <Link href="/attendance?leave=request"><CalendarOff className="h-4 w-4" /> Leave request</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
