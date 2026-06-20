"use client";

import * as React from "react";

import { BackButton } from "@/components/shell/back-button";
import { PageHeader } from "@/components/shell/page-header";
import { Tabs, type TabItem } from "@/components/ui/tabs";

import { useEmployeeOverview } from "../hooks";
import { AttendanceTab } from "./tabs/attendance-tab";
import { BenchmarksTab } from "./tabs/benchmarks-tab";
import { OverviewTab } from "./tabs/overview-tab";
import { ProjectsTab } from "./tabs/projects-tab";
import { ReportsTab } from "./tabs/reports-tab";
import { TasksTab } from "./tabs/tasks-tab";

const TABS: TabItem[] = [
  { value: "overview", label: "Overview" },
  { value: "benchmarks", label: "Benchmarks" },
  { value: "projects", label: "Projects" },
  { value: "tasks", label: "Activities" },
  { value: "reports", label: "Reports" },
  { value: "attendance", label: "Attendance" },
];

/**
 * Layer 3 — full employee detail page. Tab shell; each tab owns its data. The
 * Overview tab reuses the SAME component as the Layer 2 drawer.
 */
export function EmployeeDetailPage({ employeeId }: { employeeId: string }) {
  const [tab, setTab] = React.useState("overview");
  const { data } = useEmployeeOverview(employeeId);

  return (
    <>
      <BackButton fallback="/dashboard" />
      <PageHeader title={data?.employee_name ?? "Employee"} subtitle="Performance detail" />
      <Tabs items={TABS} value={tab} onChange={setTab} className="mb-4" />

      {tab === "overview" && <OverviewTab employeeId={employeeId} />}
      {tab === "benchmarks" && <BenchmarksTab employeeId={employeeId} />}
      {tab === "projects" && <ProjectsTab employeeId={employeeId} />}
      {tab === "tasks" && <TasksTab employeeId={employeeId} />}
      {tab === "reports" && <ReportsTab employeeId={employeeId} />}
      {tab === "attendance" && <AttendanceTab employeeId={employeeId} />}
    </>
  );
}
