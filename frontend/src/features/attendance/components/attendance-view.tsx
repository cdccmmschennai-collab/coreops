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

import { HolidayManager } from "@/features/calendar/components/holiday-manager";

import { AttendanceCalendar } from "./attendance-calendar";
import { AttendanceHistory } from "./attendance-history";
import { AttendanceKpis } from "./attendance-kpis";
import { CorrectionsPreview } from "./corrections-preview";

type TabKey =
  | "calendar"
  | "history"
  | "leave"
  | "leave-balance"
  | "corrections"
  | "holidays";

export function AttendanceView() {
  const { role, employeeId } = useAuth();
  const canManage = can(role, "attendance.manage");
  const canRequestLeave = Boolean(employeeId) && can(role, "leave.request");
  const [tab, setTab] = React.useState<TabKey>("calendar");
  const [leaveDialogOpen, setLeaveDialogOpen] = React.useState(false);

  // Deep-link: /attendance?leave=request opens the Request Leave dialog
  // (used by the employee dashboard "Leave request" quick action).
  const searchParams = useSearchParams();
  React.useEffect(() => {
    if (searchParams.get("leave") === "request" && canRequestLeave) {
      setLeaveDialogOpen(true);
    }
  }, [searchParams, canRequestLeave]);

  // Deep-link: /attendance?tab=leave selects a tab on load (used by the PM
  // dashboard "Leave requests" shortcut). leave-balance is manager-only.
  React.useEffect(() => {
    const t = searchParams.get("tab") as TabKey | null;
    if (!t) return;
    const allowed: TabKey[] = ["calendar", "history", "leave", "holidays"];
    if (canManage) allowed.push("leave-balance");
    if (features.attendanceCorrections) allowed.push("corrections");
    if (allowed.includes(t)) setTab(t);
  }, [searchParams, canManage]);

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
        items={[
          { value: "calendar", label: "Calendar" },
          { value: "history", label: "History" },
          { value: "leave", label: "Leave" },
          // Leave Balance is a manager/admin-only maintenance view.
          ...(canManage ? [{ value: "leave-balance", label: "Leave Balance" }] : []),
          // Corrections is deferred until biometric / automated attendance
          // capture exists (attendance is entered manually today). Hidden
          // behind a feature flag; see features.attendanceCorrections.
          ...(features.attendanceCorrections
            ? [{ value: "corrections", label: "Corrections" }]
            : []),
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
