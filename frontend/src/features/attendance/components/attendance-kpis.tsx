"use client";

import * as React from "react";

import { Kpi, KpiGrid } from "@/components/ui/kpi";
import { useDailySummary } from "@/features/biometric/hooks";
import { useCalendarEvents } from "@/features/calendar/hooks";
import { useMyLeaveBalance } from "@/features/leave-balances/hooks";
import { formatBalance } from "@/features/leave-balances/types";
import { PermissionRemainingKpi } from "@/features/permissions/components/permission-remaining-kpi";

import { formatPresentDays, leaveDaysTaken, presentDaysInMonth } from "../day-status";
import { useAttendanceList } from "../hooks";
import { monthRange } from "../month";
import { isCurrentMonthKey, parseMonthKey, withMonth } from "../selected-month";

interface Props {
  employeeId: string;
  /** The month every tile describes, as `YYYY-MM-01`. Owned by `AttendanceView`
   *  and shared with the calendar grid below. */
  month: string;
  /** The current business month, so a tile can say whether it is describing now
   *  or history without consulting a clock of its own. */
  currentMonth: string;
}

/**
 * The attendance KPIs for the signed-in user, FOR THE SELECTED MONTH.
 *
 * Every tile follows the calendar's month selector. Before this, the tiles read
 * `nowInIST()` and the grid read its own private state, so stepping back to
 * August left four September figures sitting over an August calendar.
 *
 * WHAT MAKES THE MONTHS DETERMINISTIC
 * ===================================
 * The month is part of every query key (the attendance/events/biometric params
 * object, `?month=` on the two balance calls), so each month is its own cache
 * entry. Stepping August -> September -> October quickly cannot land August's
 * response in October's card: a response is stored under the key it was
 * requested with, and the tiles only ever read the key for the month currently
 * selected. Coming back to August reads August's entry again and shows exactly
 * the figures it showed before.
 *
 * NOTHING IS RECALCULATED HERE THAT THE SERVER ALREADY ANSWERS. Available Leave
 * is the ledger's closing balance for the month - the frontend does no
 * `previous + allocation` arithmetic - and Permission Remaining is the server's
 * monthly figure. The only arithmetic in this file is the presence roll-up,
 * which is the existing `day-status.ts` shared with the grid.
 */
export function AttendanceKpis({ employeeId, month, currentMonth }: Props) {
  const view = parseMonthKey(month);
  const year = view?.y ?? new Date().getFullYear();
  const monthIndex = view?.m ?? new Date().getMonth();
  // A CALENDAR month, 1st to last - never a rolling 30 days.
  const { from, to } = monthRange(year, monthIndex);
  const isCurrent = isCurrentMonthKey(month, currentMonth);

  const query = useAttendanceList({
    employee_id: employeeId,
    status: "",
    from,
    to,
    limit: 100,
    offset: 0,
  });
  const items = query.data?.items ?? [];

  // The other two inputs the calendar grid resolves a day from. Requested with
  // the SAME parameters the calendar uses, so on the Calendar tab these are the
  // very same cached queries rather than extra round trips - and they move to the
  // new month at the same instant the grid does.
  const eventsQuery = useCalendarEvents({ from, to, limit: 100 });
  const biometricQuery = useDailySummary({ employeeId, from, to });

  // Available Leave is the backend ledger's closing balance FOR THIS MONTH: the
  // authoritative figure, derived server-side from
  // `carry_forward + allocation + adjustment - consumed`. Asking for a month is a
  // pure read - it accrues nothing - so stepping through months cannot change a
  // balance, and August answers the same value however often it is asked.
  const balanceQuery = useMyLeaveBalance(month);
  const balance = balanceQuery.data;

  /**
   * Present days from the RESOLVED status of every date in the month, through
   * the same `day-status.ts` the calendar cell and the day popover use - not
   * from a count of `attendance_records` rows.
   *
   * That count was the bug: a day the device fully recorded showed as Present
   * on the calendar but added nothing here until a PM manually re-entered it.
   * A biometric present day is now worth 1.0 and an officially recorded half
   * day 0.5, and the card agrees with the grid it sits above.
   *
   * Nothing is written. This is arithmetic over data already fetched.
   */
  const present = React.useMemo(
    () =>
      presentDaysInMonth({
        year,
        month: monthIndex,
        records: query.data?.items ?? [],
        events: eventsQuery.data?.items ?? [],
        summaries: biometricQuery.data?.items ?? [],
      }),
    // The query results, not the `?? []` fallbacks above - those are a fresh
    // array on every render and would defeat the memo.
    [year, monthIndex, query.data, eventsQuery.data, biometricQuery.data],
  );

  // Leave taken is the month's marked leave, IN DAYS - the same amber days the
  // grid below paints, priced the way the ledger prices them. Those rows are
  // already scoped to `from`..`to`.
  //
  // It was a COUNT of `leave` rows, which is where the half-day bug surfaced on
  // this card: a half-day leave is a `half_day` row carrying a 0.5 fraction, so
  // it was not counted at all and the tile could never show a half. `leaveDaysTaken`
  // is the frontend half of the rule in `leave_balances/ledger.py`.
  //
  // Still deliberately NOT the ledger's `consumed`: that figure excludes unpaid
  // leave and reads 0 for any month outside the employee's ledger (which begins
  // 2026-08-01, and only for the employees who had a stored balance). This card
  // has always meant "days you were marked on leave", and it still does - it now
  // means it in days rather than in rows.
  // Depends on `query.data`, not on the `items` binding above: that one is a
  // fresh `?? []` array on every render and would defeat the memo - the same
  // reason the presence memo below spells its dependency the same way.
  const leave = React.useMemo(
    () => leaveDaysTaken(query.data?.items ?? []),
    [query.data],
  );

  return (
    <KpiGrid>
      <Kpi
        // "Present this month" only while the month IS this month; a past month
        // is named outright rather than called "this month".
        label={isCurrent ? "Present this month" : withMonth("Present", month, currentMonth)}
        value={`${formatPresentDays(present)}d`}
      />
      <Kpi
        label={withMonth("Leave taken", month, currentMonth)}
        // Formatted like the Present tile beside it: `1` never renders as
        // "1.0", and a half day is never rounded away into "1" or "2".
        value={`${formatPresentDays(leave)}d`}
      />
      <Kpi
        label={withMonth("Available Leave", month, currentMonth)}
        // "-" while it loads, on error, and for a month before this employee's
        // ledger begins - which is NOT a balance of zero and must not be shown
        // as one. Zero and NEGATIVE balances print as themselves: a negative
        // balance is loss-of-pay, it is real, and nothing here hides it or
        // blocks anything because of it.
        //
        // "-" is the whole message. The "No leave ledger for July 2026." line
        // that used to sit under it explained an ordinary state - the label
        // already names the month and the dash already says there is no figure
        // - and it was the tile's only multi-line state, so it made this one
        // card taller than the three beside it. Only a genuine FAILURE still
        // gets a line, because that one is worth a second look.
        value={
          balance && balance.in_ledger
            ? `${formatBalance(balance.available_leave)}d`
            : "-"
        }
        hint={
          balanceQuery.isError ? "Couldn't load this month's balance." : undefined
        }
      />
      {/* Replaces the former "Absent" tile (Phase 11). Absent days were a count
          of what went wrong; permission hours are something the employee acts
          on, which is why the Request entry point lives in this tile and nowhere
          else. It brings its own balance query for the SELECTED month - the
          figure comes from the server, not from the attendance rows above - and
          it is the tile that decides whether a request may still be filed. */}
      <PermissionRemainingKpi month={month} isCurrentMonth={isCurrent} />
    </KpiGrid>
  );
}
