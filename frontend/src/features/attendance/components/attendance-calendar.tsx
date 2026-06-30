"use client";

import * as React from "react";
import { ChevronLeft, ChevronRight, Clock } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { nowInIST } from "@/lib/ist";
import { cn } from "@/lib/utils";

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

export function AttendanceCalendar({ employeeId }: { employeeId: string }) {
  const today = React.useMemo(() => nowInIST(), []);
  const [view, setView] = React.useState({ y: today.getFullYear(), m: today.getMonth() });

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

  const byDate = React.useMemo(() => {
    const map = new Map<string, Attendance>();
    for (const r of query.data?.items ?? []) map.set(r.attendance_date, r);
    return map;
  }, [query.data]);

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
                  <div
                    key={i}
                    className={cn(
                      "-ml-px -mt-px flex min-h-[86px] flex-col border border-border p-2",
                      s ? s.cell : "bg-card",
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
                  </div>
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
            <span className="rounded-full bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
              Preview
            </span>
          </CardHeader>
          <CardContent className="p-3.5">
            <div className="mb-2 flex items-center gap-2.5">
              <Clock className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="font-medium">General</span>
            </div>
            <div className="tabular text-sm">09:00 – 17:30</div>
            <div className="mt-1 text-xs text-muted-foreground">Asia/Kolkata · 8h day · 30m lunch</div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
