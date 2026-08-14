"use client";

import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
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
import { LeaveBalanceTab } from "@/features/leave-balances/components/leave-balance-tab";
import { features } from "@/lib/env";
import { can } from "@/lib/rbac";
import { useUrlState } from "@/lib/use-url-state";

import { HolidayManager } from "@/features/calendar/components/holiday-manager";

import { AttendanceCalendar } from "./attendance-calendar";
import { AttendanceHistory } from "./attendance-history";
import { AttendanceKpis } from "./attendance-kpis";
import { CorrectionsPreview } from "./corrections-preview";
import { attendanceTabs, resolveTab, type TabKey } from "../tabs";

export function AttendanceView() {
  const { role, employeeId } = useAuth();
  const canManage = can(role, "attendance.manage");
  const canRequestLeave = Boolean(employeeId) && can(role, "leave.request");
  // Active tab lives in the URL (also the deep-link target used by the PM
  // dashboard "Leave requests" shortcut, /attendance?tab=leave), so switching
  // tabs and returning to the page keeps the same tab.
  const [rawTab, setTab] = useUrlState("tab", "calendar");
  const [leaveDialogOpen, setLeaveDialogOpen] = React.useState(false);

  // Deep-link: /attendance?leave=request opens the Request Leave dialog
  // (used by the employee dashboard "Leave request" quick action).
  const searchParams = useSearchParams();
  React.useEffect(() => {
    if (searchParams.get("leave") === "request" && canRequestLeave) {
      setLeaveDialogOpen(true);
    }
  }, [searchParams, canRequestLeave]);

  // Which tabs exist for this user, and which one the URL selects. Both come
  // from the pure `tabs.ts` config so the labels are unit-testable - this repo
  // has no DOM test harness, so a label inside JSX cannot be asserted on.
  const tabOptions = {
    canManage,
    correctionsEnabled: features.attendanceCorrections,
  };
  const tab = resolveTab(rawTab, tabOptions);

  const actions = (
    <>
      <Button variant="secondary" onClick={() => toast.info("Export - coming soon")}>
        <Download className="h-4 w-4" />
        Export
      </Button>
      {canRequestLeave && (
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
        subtitle="Track presence, shifts, and leave."
        actions={actions}
      />

      {employeeId && <AttendanceKpis employeeId={employeeId} />}

      <Tabs
        className="mb-4"
        value={tab}
        onChange={(v) => setTab(v as TabKey)}
        items={attendanceTabs(tabOptions)}
      />

      {tab === "calendar" &&
        (employeeId ? (
          <AttendanceCalendar employeeId={employeeId} />
        ) : (
          <EmptyState
            title="No personal calendar"
            description="Your account isn't linked to an employee profile, so there's no personal attendance calendar. Use the Records tab to browse attendance."
          />
        ))}
      {tab === "history" && <AttendanceHistory />}
      {tab === "leave" && <LeaveTab />}
      {tab === "leave-balance" && canManage && <LeaveBalanceTab />}
      {features.attendanceCorrections && tab === "corrections" && <CorrectionsPreview />}
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
