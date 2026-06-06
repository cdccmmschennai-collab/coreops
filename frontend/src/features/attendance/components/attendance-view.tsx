"use client";

import * as React from "react";
import Link from "next/link";
import { CalendarOff, Download, Plus } from "lucide-react";
import { toast } from "sonner";

import { EmptyState } from "@/components/feedback/empty-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs } from "@/components/ui/tabs";
import { useAuth } from "@/features/auth/auth-provider";
import { LeaveRequestDialog } from "@/features/leave/components/leave-request-dialog";
import { LeaveTab } from "@/features/leave/components/leave-tab";
import { can } from "@/lib/rbac";

import { HolidayManager } from "@/features/calendar/components/holiday-manager";

import { AttendanceCalendar } from "./attendance-calendar";
import { AttendanceHistory } from "./attendance-history";
import { AttendanceKpis } from "./attendance-kpis";
import { CorrectionsPreview } from "./corrections-preview";

type TabKey = "calendar" | "history" | "leave" | "corrections" | "holidays";

export function AttendanceView() {
  const { role, employeeId } = useAuth();
  const canManage = can(role, "attendance.manage");
  const [tab, setTab] = React.useState<TabKey>("calendar");
  const [leaveDialogOpen, setLeaveDialogOpen] = React.useState(false);

  const actions = (
    <>
      <Button variant="secondary" onClick={() => toast.info("Export - coming soon")}>
        <Download className="h-4 w-4" />
        Export
      </Button>
      {employeeId && can(role, "leave.request") && (
        <Button variant="secondary" onClick={() => setLeaveDialogOpen(true)}>
          <CalendarOff className="h-4 w-4" />
          Request Leave
        </Button>
      )}
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
        subtitle="Track presence, shifts, and leave. Corrections can be requested up to 7 days back."
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
          { value: "leave", label: "Leave" },
          { value: "corrections", label: "Corrections" },
          { value: "holidays", label: "Holidays" },
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
      {tab === "leave" && <LeaveTab />}
      {tab === "corrections" && <CorrectionsPreview />}
      {tab === "holidays" && <HolidayManager />}

      {/* Request Leave modal */}
      {leaveDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-foreground/40"
            onClick={() => setLeaveDialogOpen(false)}
            aria-hidden
          />
          <Card className="relative z-10 w-full max-w-md shadow-xl">
            <CardHeader className="border-b border-border px-5 py-3.5">
              <CardTitle className="text-base">Request Leave</CardTitle>
            </CardHeader>
            <CardContent className="pt-5">
              <LeaveRequestDialog onClose={() => setLeaveDialogOpen(false)} />
            </CardContent>
          </Card>
        </div>
      )}
    </>
  );
}
