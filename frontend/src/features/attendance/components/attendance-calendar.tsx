"use client";

import * as React from "react";
import { ChevronLeft, ChevronRight, Clock, Fingerprint } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { nowInIST } from "@/lib/ist";
import { cn } from "@/lib/utils";

import { AttendanceDayPopover } from "@/features/biometric/components/attendance-day-popover";
import {
  formatPermission,
  formatShiftWindow,
  statusWithPermission,
  type ResolvedDayStatus,
} from "@/features/biometric/day-detail";
import { useDailySummary } from "@/features/biometric/hooks";
import { formatISTTime } from "@/features/biometric/mapping-format";
import type { DailySummary } from "@/features/biometric/types";
import { useCalendarEvents } from "@/features/calendar/hooks";

import { calendarDayMaps, resolveAttendanceDay } from "../day-status";
import { useAttendanceList } from "../hooks";
import {
  DOW,
  MONTHS,
  daysInMonth,
  firstDowMonday,
  isoDate,
  isWeekend,
  monthRange,
} from "../month";
import { parseMonthKey, shiftMonthKey } from "../selected-month";
import type { Attendance, AttendanceStatus } from "../types";

type StatusKey = AttendanceStatus;

const STATUS: Record<StatusKey, { cell: string; text: string; dot: string; label: string }> = {
  present:  { cell: "bg-emerald-50", text: "text-emerald-700", dot: "bg-emerald-500", label: "Present" },
  absent:   { cell: "bg-red-50",     text: "text-red-700",     dot: "bg-red-500",     label: "Absent" },
  half_day: { cell: "bg-slate-100",  text: "text-slate-700",   dot: "bg-slate-500",   label: "Half day" },
  leave:    { cell: "bg-amber-50",   text: "text-amber-700",   dot: "bg-amber-500",   label: "Leave" },
  comp_off: { cell: "bg-teal-50",    text: "text-teal-700",    dot: "bg-teal-500",    label: "Comp off" },
  holiday:  { cell: "bg-violet-50",  text: "text-violet-700",  dot: "bg-violet-500",  label: "Holiday" },
  weekend:  { cell: "bg-slate-50",   text: "text-muted-foreground", dot: "bg-slate-300", label: "Weekend" },
};

/**
 * Whether the calendar cell shows its biometric punch line.
 *
 * OFF since 2026-08-18. The punches currently in the database are backfill/test
 * data, and a cell reading "09:18 AM - 05:53 PM" presents them as this
 * employee's real attendance. Until the live device feed is connected, the cell
 * shows the date and the official status only.
 *
 * This hides a PRESENTATION, nothing else. No punch is deleted, no query is
 * removed, and `BiometricTimes` below is untouched: the same
 * `useDailySummary` data still drives the day popover, the Records screens and
 * the permission indicator. Flip this one constant to `true` when the real
 * punches arrive and the line returns exactly as it was.
 */
const SHOW_CALENDAR_PUNCH_TIMES = false;

/**
 * First and last biometric punch for one day, inside the existing calendar cell.
 *
 * Kept deliberately quiet - muted, tabular, one line - because it sits BESIDE the
 * attendance status, which remains the official record. It is never allowed to
 * look like a decision the system made:
 *   - a missing OUT renders as "--:--", not as a guessed time
 *   - the title spells out what the two numbers actually are, since EasyTime
 *     reports no IN/OUT direction and these are boundary punches
 *
 * Deliberately reads `punch_times`/`kept_count` - the RAW, un-merged device
 * evidence - never `summary.first_in`/`last_out` (Phase 9C: those are the
 * FINALIZED result and may include a PM-entered time). This is the one place
 * on the calendar with a Fingerprint icon, so it must never show a PM-entered
 * time as if the device recorded it.
 */
function BiometricTimes({ summary }: { summary: DailySummary }) {
  if (summary.kept_count === 0) return null;

  const firstPunch = summary.punch_times[0];
  const lastPunch = summary.kept_count >= 2 ? summary.punch_times[summary.punch_times.length - 1] : null;

  const collapsed = summary.kept_count < summary.punch_count;
  const title =
    `First punch ${formatISTTime(firstPunch)}, ` +
    (lastPunch
      ? `last punch ${formatISTTime(lastPunch)}`
      : "no second punch recorded") +
    ` (IST). ${summary.punch_count} punch${summary.punch_count === 1 ? "" : "es"}` +
    (collapsed ? `, ${summary.kept_count} after removing repeat scans` : "") +
    ".";

  return (
    <div
      className="mt-1 flex items-center gap-1 tabular text-[10px] leading-none text-muted-foreground"
      title={title}
    >
      <Fingerprint className="h-2.5 w-2.5 shrink-0" aria-hidden />
      <span>{formatISTTime(firstPunch)}</span>
      <span aria-hidden>-</span>
      <span className={cn(!lastPunch && "opacity-60")}>
        {formatISTTime(lastPunch)}
      </span>
    </div>
  );
}

interface Props {
  employeeId: string;
  /** The month to draw, as `YYYY-MM-01`. Owned by `AttendanceView` so the KPI
   *  cards above the tabs describe the very same month this grid shows. */
  month: string;
  /** The current business month - what the "Today" button returns to. */
  currentMonth: string;
  onMonthChange: (month: string) => void;
}

/** The month grid. It still owns the ONLY month control on the page (Previous /
 *  Today / Next in its header); what changed is that the control now sets page
 *  state instead of a private `useState`, so everything month-scoped moves
 *  together. */
export function AttendanceCalendar({
  employeeId,
  month,
  currentMonth,
  onMonthChange,
}: Props) {
  const today = React.useMemo(() => nowInIST(), []);
  // The controlled month, in the `{y, m}` shape the grid arithmetic wants. The
  // `??` arm is unreachable in practice - `AttendanceView` normalises the value
  // before it gets here - and exists so a bad prop cannot crash the grid.
  const view = React.useMemo(
    () => parseMonthKey(month) ?? { y: today.getFullYear(), m: today.getMonth() },
    [month, today],
  );
  // The open day, plus the cell element the popover anchors to. Held here (not in
  // the URL) so opening a day cannot navigate, and the month view never resets.
  const [selected, setSelected] = React.useState<{
    iso: string;
    anchor: HTMLElement;
  } | null>(null);

  /** Click a day to open it; click the same day again to close. */
  const toggleDay = React.useCallback(
    (iso: string, anchor: HTMLElement) => {
      setSelected((prev) => (prev?.iso === iso ? null : { iso, anchor }));
    },
    [],
  );

  // Changing month must not leave a popover pointing at a cell that now shows a
  // different date - the anchor element is reused by React across renders.
  React.useEffect(() => {
    setSelected(null);
  }, [view.y, view.m]);

  const { from, to } = monthRange(view.y, view.m);
  const query = useAttendanceList({
    employee_id: employeeId,
    status: "",
    from,
    to,
    limit: 100,
    offset: 0,
  });

  const eventsQuery = useCalendarEvents({ from, to, limit: 100 });

  // Biometric first-punch / last-punch for the same window. Observation only:
  // it is shown beside the official record and never replaces its status.
  const biometricQuery = useDailySummary({ employeeId, from, to });

  const byDate = React.useMemo(() => {
    const map = new Map<string, Attendance>();
    for (const r of query.data?.items ?? []) map.set(r.attendance_date, r);
    return map;
  }, [query.data]);

  const biometricByDate = React.useMemo(() => {
    const map = new Map<string, DailySummary>();
    for (const s of biometricQuery.data?.items ?? []) map.set(s.summary_date, s);
    return map;
  }, [biometricQuery.data]);

  // The employee's contracted office hours, from the same request. Null when they
  // have no office - the panel and the Shift card both cope with that.
  const schedule = biometricQuery.data?.schedule ?? null;
  const shiftWindow = formatShiftWindow(
    schedule?.shift_start ?? null,
    schedule?.shift_end ?? null,
  );

  // Office-closing events (holiday / CDC holiday / natural hazard) and
  // "office open on a normally-off day" overrides, keyed by date. Built by the
  // shared `calendarDayMaps` so the "Present this month" card reads these
  // entries exactly the way the grid does.
  const { off: offByDate, working: workingByDate } = React.useMemo(
    () => calendarDayMaps(eventsQuery.data?.items ?? []),
    [eventsQuery.data],
  );

  /**
   * The one status resolution for a date, shared by the grid and the popover.
   *
   * Both the cell below and `AttendanceDayPopover` at the bottom of this file
   * read THIS - there is no second status calculation for the calendar. A day
   * the device fully recorded but nobody has ruled on used to render as an empty
   * cell whose popover said "Present"; it now says Present in both places,
   * because both places are asking the same function.
   *
   * The order itself lives in `day-status.ts` rather than inline here, because
   * the "Present this month" card has to resolve a day the same way this grid
   * does: attendance record, then biometric `present`, then the company
   * calendar (a declared working day, an office-closing entry, the weekend).
   *
   * A punched day therefore reads Present even on a 2nd Saturday, a holiday or
   * a hazard day, with no PM action - the calendar entry decides only the days
   * nobody punched, and its title still prints in the cell as context.
   */
  const statusFor = React.useCallback(
    (iso: string): ResolvedDayStatus<StatusKey> | null => {
      const [y, m, d] = iso.split("-").map(Number);
      return resolveAttendanceDay({
        recordStatus: byDate.get(iso)?.status,
        // Read by truthiness, exactly as the cell has always read these two maps
        // - a titleless event must keep behaving the way it did.
        declaredWorking: Boolean(workingByDate.get(iso)),
        officeClosed: Boolean(offByDate.get(iso)),
        weekend: isWeekend(y, m - 1, d),
        // The same `buildDayDetail` the popover calls, on the same row - so the
        // defensive "a row without a first_in is no_record" rule applies
        // identically on both sides and cannot drift.
        summary: biometricByDate.get(iso),
      });
    },
    [byDate, workingByDate, offByDate, biometricByDate],
  );

  /** The open day's status - the very same value its cell rendered. */
  const selectedStatus = selected ? statusFor(selected.iso) : null;

  const todayIso = isoDate(today.getFullYear(), today.getMonth(), today.getDate());

  const total = daysInMonth(view.y, view.m);
  const lead = firstDowMonday(view.y, view.m);
  const cells: (number | null)[] = [
    ...Array.from({ length: lead }, () => null),
    ...Array.from({ length: total }, (_, i) => i + 1),
  ];
  while (cells.length % 7 !== 0) cells.push(null);

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0 border-b border-border p-4">
          <CardTitle className="text-base">
            {MONTHS[view.m]} {view.y}
          </CardTitle>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Previous month"
              onClick={() => onMonthChange(shiftMonthKey(month, -1))}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onMonthChange(currentMonth)}
            >
              Today
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Next month"
              onClick={() => onMonthChange(shiftMonthKey(month, 1))}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-4">
          {query.isLoading ? (
            <Skeleton className="h-[520px] w-full" />
          ) : (
            <div className="grid grid-cols-7">
              {DOW.map((d) => (
                <div
                  key={d}
                  className="px-2.5 py-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
                >
                  {d}
                </div>
              ))}
              {cells.map((day, i) => {
                if (day == null) return <div key={i} className="min-h-[86px]" />;
                const iso = isoDate(view.y, view.m, day);
                const record = byDate.get(iso);
                const bio = biometricByDate.get(iso);
                const holidayTitle = offByDate.get(iso);
                const workingTitle = workingByDate.get(iso);
                // A declared working day overrides weekends and holidays — the
                // office is open, so the day renders as a normal working day.
                // That precedence lives in `statusFor`, which the popover reads
                // too; nothing here decides a status on its own.
                const resolved = statusFor(iso);
                const s = resolved ? STATUS[resolved.key] : null;
                const isToday = iso === todayIso;
                return (
                  <button
                    key={i}
                    type="button"
                    // A real button, so the grid is keyboard- and
                    // screen-reader-navigable rather than click-only.
                    onClick={(e) => toggleDay(iso, e.currentTarget)}
                    aria-label={`Attendance for ${iso}`}
                    aria-expanded={iso === selected?.iso}
                    className={cn(
                      "-ml-px -mt-px flex min-h-[86px] flex-col border border-border p-2 text-left",
                      "transition-colors hover:bg-accent/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset",
                      s ? s.cell : "bg-card",
                      // Subtle, and it keeps the cell's own colour: the popover's
                      // caret already does the work of connecting the two.
                      iso === selected?.iso &&
                        "relative z-10 ring-2 ring-inset ring-primary/70",
                    )}
                  >
                    <div className="flex items-center gap-1.5">
                      <span
                        className={cn(
                          "tabular text-[13px]",
                          isToday ? "font-bold text-primary" : cn("font-medium", s?.text ?? "text-foreground"),
                        )}
                      >
                        {day}
                      </span>
                      {isToday && (
                        <span className="text-[9px] font-bold tracking-wider text-primary">TODAY</span>
                      )}
                    </div>
                    {holidayTitle && !workingTitle && !record && (
                      <p className="mt-1 text-[10px] font-medium text-violet-700 leading-tight line-clamp-2">
                        {holidayTitle}
                      </p>
                    )}
                    {workingTitle && !record && (
                      <p className="mt-1 text-[10px] font-medium text-emerald-700 leading-tight line-clamp-2">
                        {workingTitle}
                      </p>
                    )}
                    {SHOW_CALENDAR_PUNCH_TIMES && bio && <BiometricTimes summary={bio} />}
                    {/* Phase 12: an approved permission is APPENDED to the
                        day's own status - "Present | 1hr" - never substituted
                        for it. The biometric line above is untouched, and the
                        cell's colour still comes from the attendance status
                        alone, so a permission changes no day's classification. */}
                    {s && (
                      <div
                        className={cn("mt-auto flex items-center gap-1.5 text-[11px] font-medium", s.text)}
                        // Same indicator either way - the day IS Present, and a
                        // second Present style would suggest two kinds of it.
                        // The provenance is stated on hover instead, because a
                        // day nobody has ruled on is still a day nobody has
                        // ruled on, and the cell must not imply otherwise.
                        title={
                          resolved?.source === "biometric"
                            ? "From the biometric record. No manager entry for this day yet."
                            : undefined
                        }
                      >
                        <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} />
                        {statusWithPermission(s.label, bio?.permission_hours)}
                      </div>
                    )}
                    {/* A permission on a day nobody has ruled on yet. Without
                        this the hours would silently vanish from the calendar
                        until a PM entered a status, and the employee would have
                        no way to see their permission was applied. Same quiet
                        line shape; a neutral dot, because it states no verdict. */}
                    {!s && bio?.permission_hours != null && (
                      <div className="mt-auto flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
                        <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                        Permission {formatPermission(bio.permission_hours)}
                      </div>
                    )}
                    {workingTitle && !record && (
                      <div className="mt-auto flex items-center gap-1.5 text-[11px] font-medium text-emerald-700">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                        Working
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="flex flex-col gap-4">
        <Card>
          <CardHeader className="border-b border-border p-4">
            <CardTitle className="text-base">Legend</CardTitle>
          </CardHeader>
          <CardContent className="p-3.5">
            {Object.entries(STATUS).map(([k, s]) => (
              <div key={k} className="flex items-center gap-2.5 py-1 text-sm">
                <span className={cn("flex h-3.5 w-3.5 items-center justify-center rounded", s.cell)}>
                  <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} />
                </span>
                <span>{s.label}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0 border-b border-border p-4">
            <CardTitle className="text-base">Shift</CardTitle>
            {!schedule && (
              <span className="rounded-full bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                Preview
              </span>
            )}
          </CardHeader>
          <CardContent className="p-3.5">
            <div className="mb-2 flex items-center gap-2.5">
              <Clock className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="font-medium">{schedule?.office_name ?? "General"}</span>
            </div>
            {/* Real office hours when the employee has an office; a placeholder
                only when they do not. The backend applies its own documented
                fallback in that case (biometric/constants.py), which is why no
                duration is claimed here. */}
            <div className="tabular text-sm">
              {shiftWindow ?? "09:00 AM - 05:30 PM"}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {schedule
                ? `${schedule.timezone ?? "Asia/Kolkata"}${
                    schedule.break_minutes != null
                      ? ` · ${schedule.break_minutes}m lunch`
                      : ""
                  }`
                : "Asia/Kolkata · no office assigned"}
            </div>
          </CardContent>
        </Card>
      </div>

      <AttendanceDayPopover
        anchor={selected?.anchor ?? null}
        title={selected ? formatDayLabel(selected.iso) : ""}
        summary={selected ? biometricByDate.get(selected.iso) : undefined}
        // The SAME resolution the cell rendered, so the panel can never contradict
        // the day that opened it. When it resolves to nothing the popover keeps
        // its own fallback and names the classification ("Incomplete", "No
        // biometric record") - an unsettled day is described, never given a status.
        attendanceLabel={selectedStatus ? STATUS[selectedStatus.key].label : null}
        // Why a manager set this day this way, in their words. This is how an
        // employee finds out that their missing evening punch was accounted for.
        reason={selected ? (byDate.get(selected.iso)?.note ?? null) : null}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}

/** `"2026-07-29"` -> `"Wednesday, 29 July 2026"`. Parsed as a plain calendar date
 *  (no zone conversion): the ISO string is already the IST attendance day. */
function formatDayLabel(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", {
    timeZone: "UTC",
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}
