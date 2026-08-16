"use client";

import * as React from "react";
import { ChevronLeft, ChevronRight, Clock, Fingerprint } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { nowInIST } from "@/lib/ist";
import { cn } from "@/lib/utils";

import { AttendanceDayPopover } from "@/features/biometric/components/attendance-day-popover";
import { formatShiftWindow } from "@/features/biometric/day-detail";
import { useDailySummary } from "@/features/biometric/hooks";
import { formatISTTime } from "@/features/biometric/mapping-format";
import type { DailySummary } from "@/features/biometric/types";
import { useCalendarEvents } from "@/features/calendar/hooks";
import { isOffEvent } from "@/features/calendar/types";

import { useAttendanceList } from "../hooks";
import {
  DOW,
  MONTHS,
  daysInMonth,
  firstDowMonday,
  isoDate,
  isWeekend,
  monthRange,
  nextMonth,
  prevMonth,
} from "../month";
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

export function AttendanceCalendar({ employeeId }: { employeeId: string }) {
  const today = React.useMemo(() => nowInIST(), []);
  const [view, setView] = React.useState({ y: today.getFullYear(), m: today.getMonth() });
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

  // Office-closing events (holiday / CDC holiday / natural hazard) keyed by date.
  const offByDate = React.useMemo(() => {
    const map = new Map<string, string>();
    for (const ev of eventsQuery.data?.items ?? []) {
      if (isOffEvent(ev.event_type)) map.set(ev.event_date, ev.title);
    }
    return map;
  }, [eventsQuery.data]);

  // "Office open on a normally-off day" overrides, keyed by date.
  const workingByDate = React.useMemo(() => {
    const map = new Map<string, string>();
    for (const ev of eventsQuery.data?.items ?? []) {
      if (ev.event_type === "working_day") map.set(ev.event_date, ev.title);
    }
    return map;
  }, [eventsQuery.data]);

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
              onClick={() => setView(prevMonth(view.y, view.m))}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setView({ y: today.getFullYear(), m: today.getMonth() })}
            >
              Today
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Next month"
              onClick={() => setView(nextMonth(view.y, view.m))}
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
                const status: StatusKey | undefined =
                  record?.status ??
                  (workingTitle
                    ? undefined
                    : holidayTitle
                      ? "holiday"
                      : isWeekend(view.y, view.m, day)
                        ? "weekend"
                        : undefined);
                const s = status ? STATUS[status] : null;
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
                    {bio && <BiometricTimes summary={bio} />}
                    {s && (
                      <div className={cn("mt-auto flex items-center gap-1.5 text-[11px] font-medium", s.text)}>
                        <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} />
                        {s.label}
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
              {shiftWindow ?? "09:00 - 17:30"}
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
        attendanceLabel={
          selected ? (statusLabelFor(byDate.get(selected.iso)?.status) ?? null) : null
        }
        // Why a manager set this day this way, in their words. This is how an
        // employee finds out that their missing evening punch was accounted for.
        reason={selected ? (byDate.get(selected.iso)?.note ?? null) : null}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}

/** The official attendance status label for a day, when a record exists. It wins
 *  over the biometric label in the popover - observation never overrules the
 *  record. Reuses the STATUS map the calendar already renders. */
function statusLabelFor(status: AttendanceStatus | undefined): string | undefined {
  return status ? STATUS[status]?.label : undefined;
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
