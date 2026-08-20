"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { CalendarOff, Download } from "lucide-react";
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
import { AttendanceKpis } from "./attendance-kpis";
import { AttendanceRecords } from "./attendance-records";
import { CorrectionsPreview } from "./corrections-preview";
import { businessMonthKey, normalizeMonthKey } from "../selected-month";
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

  /**
   * THE SELECTED MONTH - one value for the whole page.
   *
   * It used to live inside `AttendanceCalendar` while the KPI cards read the
   * clock, so the tiles said September while the grid drew August. The calendar's
   * own Prev/Today/Next controls still drive it (there is no second selector);
   * they now set state that the cards read too.
   *
   * In the URL (`att_month`) for the same reason the tab is: going into a day, a
   * leave request or a permission detail and pressing Back returns to the month
   * you were reading. `useUrlState` strips the parameter whenever it equals the
   * fallback, so a bare /attendance is the current month by construction.
   *
   * `currentMonth` is resolved ONCE per mount from the Chennai business calendar,
   * so "is this the current month" cannot flicker mid-session.
   */
  const currentMonth = React.useMemo(() => businessMonthKey(), []);
  const [rawMonth, setMonth] = useUrlState("att_month", currentMonth);
  // A hand-typed ?att_month=banana must not send nonsense to four APIs.
  const month = normalizeMonthKey(rawMonth, currentMonth);

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
    </>
  );

  return (
    <>
      <PageHeader
        title="Attendance"
        subtitle="Track presence, shifts, and leave."
        actions={actions}
      />

      {employeeId && (
        <AttendanceKpis
          employeeId={employeeId}
          month={month}
          currentMonth={currentMonth}
        />
      )}

      <Tabs
        className="mb-4"
        value={tab}
        onChange={(v) => setTab(v as TabKey)}
        items={attendanceTabs(tabOptions)}
      />

      {tab === "calendar" &&
        (employeeId ? (
          <AttendanceCalendar
            employeeId={employeeId}
            month={month}
            currentMonth={currentMonth}
            onMonthChange={setMonth}
          />
        ) : (
          <EmptyState
            title="No personal calendar"
            description={
              canManage
                ? "Your account isn't linked to an employee profile, so there's no personal attendance calendar. Use the Records tab to review the team's day."
                : "Your account isn't linked to an employee profile, so there's no personal attendance calendar. Ask your manager to link your employee record."
            }
          />
        ))}
      {/* Records = the PM daily review. Manager-only, and guarded here as well
          as in the tab list so a hand-typed ?tab=history cannot reach it. */}
      {tab === "history" && canManage && <AttendanceRecords />}
      {tab === "leave" && <LeaveTab />}
      {/* Same selected month as the cards and the grid: the balances a manager
          reads here are the ones the employee sees on their own tiles. */}
      {tab === "leave-balance" && canManage && (
        <LeaveBalanceTab month={month} currentMonth={currentMonth} />
      )}
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
