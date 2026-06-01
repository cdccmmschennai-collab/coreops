"use client";

import * as React from "react";
import Link from "next/link";
import { Download, Plus } from "lucide-react";
import { toast } from "sonner";

import { EmptyState } from "@/components/feedback/empty-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Tabs } from "@/components/ui/tabs";
import { useAuth } from "@/features/auth/auth-provider";
import { can } from "@/lib/rbac";

import { AttendanceCalendar } from "./attendance-calendar";
import { AttendanceHistory } from "./attendance-history";
import { AttendanceKpis } from "./attendance-kpis";
import { CorrectionsPreview } from "./corrections-preview";
import { LeaveBalancesPreview } from "./leave-balances-preview";

type TabKey = "calendar" | "history" | "balances" | "corrections";

export function AttendanceView() {
  const { role, employeeId } = useAuth();
  const canManage = can(role, "attendance.manage");
  const [tab, setTab] = React.useState<TabKey>("calendar");

  const actions = (
    <>
      <Button variant="secondary" onClick={() => toast.info("Export — coming soon")}>
        <Download className="h-4 w-4" />
        Export
      </Button>
      {canManage && (
        <Button asChild>
          <Link href="/attendance/new">
            <Plus className="h-4 w-4" />
            Record attendance
          </Link>
        </Button>
      )}
    </>
  );

  return (
    <>
      <PageHeader
        title="Attendance"
        subtitle="Track presence, shifts, and leave balances. Corrections can be requested up to 7 days back."
        actions={actions}
      />

      {employeeId && <AttendanceKpis employeeId={employeeId} />}

      <Tabs
        className="mb-4"
        value={tab}
        onChange={(v) => setTab(v as TabKey)}
        items={[
          { value: "calendar", label: "Calendar" },
          { value: "history", label: "History" },
          { value: "balances", label: "Leave balances" },
          { value: "corrections", label: "Corrections", count: 3 },
        ]}
      />

      {tab === "calendar" &&
        (employeeId ? (
          <AttendanceCalendar employeeId={employeeId} />
        ) : (
          <EmptyState
            title="No personal calendar"
            description="Your account isn't linked to an employee profile, so there's no personal attendance calendar. Use the History tab to browse records."
          />
        ))}
      {tab === "history" && <AttendanceHistory />}
      {tab === "balances" && <LeaveBalancesPreview />}
      {tab === "corrections" && <CorrectionsPreview />}
    </>
  );
}
