"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight, Plus } from "lucide-react";

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
import { useProjects } from "@/features/projects/hooks";
import { StatusBadge } from "@/features/work-reports/components/status-badge";
import { useWorkReportList } from "@/features/work-reports/hooks";
import { formatMinutes } from "@/lib/format";

import { greeting, todayISO, weekStartISO } from "./utils";

const DOW_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const CHART_COLORS = ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444", "#6366f1"];

// ── sub-components ────────────────────────────────────────────────────────────

function WeekBars({ data }: { data: { date: string; minutes: number }[] }) {
  const maxMin = Math.max(...data.map((d) => d.minutes), 1);
  const maxH    = Math.ceil((maxMin / 60) / 3) * 3; // round up to nearest 3h

  return (
    <svg viewBox="0 0 560 180" width="100%" style={{ display: "block" }}>
      {/* grid lines */}
      <g stroke="hsl(var(--border))" strokeDasharray="2 3" fill="none">
        {[20, 60, 100, 140].map((y) => (
          <line key={y} x1="36" y1={y} x2="556" y2={y} />
        ))}
      </g>
      {/* y-axis labels */}
      <g fontSize="10" fill="hsl(var(--muted-foreground))" textAnchor="end" fontFamily="var(--font-mono)">
        {[maxH, (maxH * 2) / 3, maxH / 3, 0].map((h, i) => (
          <text key={i} x="32" y={20 + i * 40}>{h}h</text>
        ))}
      </g>
      {/* bars */}
      {data.map((d, i) => {
        const x   = 60 + i * 72;
        const pct = d.minutes / (maxH * 60);
        const barH = Math.max(pct * 120, d.minutes > 0 ? 2 : 0);
        const y   = 140 - barH;
        return (
          <g key={i}>
            {d.minutes > 0 && (
              <rect x={x} y={y} width="44" height={barH} rx="3"
                fill="hsl(var(--primary))" opacity={0.85} />
            )}
            <text x={x + 22} y="162" fontSize="10" textAnchor="middle"
              fill="hsl(var(--muted-foreground))" fontFamily="var(--font-mono)">
              {DOW_SHORT[i]}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

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
  const { user, employee, employeeId } = useAuth();

  // Greet by employee full name — never the username/email/login id.
  // Resolution order: Employee.full_name (from /auth/me) → username fallback.
  const displayName =
    employee?.full_name?.trim() || user?.email.split("@")[0] || "there";
  const today     = React.useMemo(todayISO, []);
  const weekStart = React.useMemo(weekStartISO, []);

  // work reports this week (own)
  const weekReports = useWorkReportList({
    employee_id: employeeId ?? "",
    project_id: "",
    status: "",
    from: weekStart,
    to: today,
    limit: 100,
    offset: 0,
  });

  // recent reports (own, last 7)
  const recentReports = useWorkReportList({
    employee_id: employeeId ?? "",
    project_id: "",
    status: "",
    from: "",
    to: "",
    limit: 7,
    offset: 0,
  });

  // active projects sidebar
  const projects = useProjects({ q: "", status: "active", limit: 6, offset: 0 });

  // ── KPI computations ──────────────────────────────────────────────────────
  const weekItems  = weekReports.data?.items ?? [];
  const hoursTotal = weekItems.reduce((s, r) => s + r.total_minutes, 0);
  const submitted  = weekItems.filter((r) => r.status !== "draft").length;
  const inReview   = weekItems.filter((r) => r.status === "submitted").length;

  // ── week chart data (Mon–Sun) ─────────────────────────────────────────────
  const chartData = React.useMemo(() => {
    const map = new Map<string, number>();
    for (const r of weekItems) map.set(r.report_date, r.total_minutes);
    return DOW_SHORT.map((_, i) => {
      const d = new Date(weekStart);
      d.setDate(d.getDate() + i);
      const iso = d.toISOString().slice(0, 10);
      return { date: iso, minutes: map.get(iso) ?? 0 };
    });
  }, [weekItems, weekStart]);

  const weekLabel = React.useMemo(() => {
    const start = new Date(weekStart);
    const end   = new Date(weekStart);
    end.setDate(end.getDate() + 6);
    return `${start.toLocaleDateString([], { month: "short", day: "numeric" })} – ${end.toLocaleDateString([], { month: "short", day: "numeric" })}`;
  }, [weekStart]);

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

      <KpiGrid>
        <Kpi
          label="Hours logged this week"
          value={formatMinutes(hoursTotal)}
        />
        <Kpi
          label="Reports this week"
          value={`${submitted} / ${weekItems.length}`}
        />
        <Kpi label="In review" value={String(inReview)} />
        <Kpi
          label="Approved"
          value={String(weekItems.filter((r) => r.status === "approved").length)}
        />
      </KpiGrid>

      {/* main two-column grid */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        {/* recent reports */}
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
                  <TableHead>Projects</TableHead>
                  <TableHead>Hours</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(recentReports.data?.items ?? []).map((r) => {
                  const uniqueProjects = [...new Set(r.tasks.map((t) => t.project_id))].length;
                  return (
                    <TableRow
                      key={r.id}
                      className="cursor-pointer"
                      onClick={() => window.location.assign(`/work-reports/${r.id}`)}
                    >
                      <TableCell className="font-medium tabular">{r.report_date}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {r.tasks.length === 0
                          ? "—"
                          : uniqueProjects === 1
                            ? `${r.tasks.length} task${r.tasks.length > 1 ? "s" : ""}`
                            : `${uniqueProjects} projects`}
                      </TableCell>
                      <TableCell className="tabular">{formatMinutes(r.total_minutes)}</TableCell>
                      <TableCell><StatusBadge status={r.status} /></TableCell>
                    </TableRow>
                  );
                })}
                {(recentReports.data?.items ?? []).length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="py-8 text-center text-sm text-muted-foreground">
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

        {/* my projects */}
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
                  className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-foreground transition-colors hover:bg-secondary"
                >
                  <ProjectDot i={i} />
                  <span className="min-w-0 flex-1 truncate">{p.name}</span>
                  <span className="tabular text-xs text-muted-foreground">{p.code}</span>
                </Link>
              ))
            )}
            {!projects.isLoading && (projects.data?.items ?? []).length === 0 && (
              <p className="px-3 py-4 text-sm text-muted-foreground">No active projects.</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* bottom two-column grid */}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {/* hours chart */}
        <Card>
          <CardHeader className="border-b border-border px-5 py-3.5">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Hours this week</CardTitle>
              <span className="text-xs text-muted-foreground">{weekLabel}</span>
            </div>
          </CardHeader>
          <CardContent className="px-5 pb-4 pt-4">
            {weekReports.isLoading
              ? <Skeleton className="h-[180px] w-full" />
              : <WeekBars data={chartData} />
            }
          </CardContent>
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
                <Link href="/reports"><ArrowRight className="h-4 w-4" /> All my reports</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
