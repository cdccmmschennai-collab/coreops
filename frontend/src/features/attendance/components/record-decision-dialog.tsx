"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  formatISTTime,
  istTimeInputValue,
} from "@/features/biometric/mapping-format";
import { formatWorked } from "@/features/biometric/review";
import type { DailyReviewRow } from "@/features/biometric/types";

import { useCreateAttendance, useUpdateAttendance } from "../hooks";
import { ATTENDANCE_STATUSES, ATTENDANCE_STATUS_LABEL } from "../schemas";
import type { AttendanceStatus } from "../types";

/**
 * The PM's decision on one employee-day.
 *
 * THE SPLIT THIS DIALOG ENFORCES: the biometric block at the top is evidence and
 * is read-only - punches are immutable and no edit here rewrites one. The form
 * below writes the OFFICIAL record in `attendance_records`, which is the only
 * place a human decision about a day is allowed to live. Two different things,
 * shown together precisely so the PM decides against the evidence rather than
 * from memory.
 *
 * It goes through the attendance module's own endpoints, so its validation
 * (check-out cannot precede check-in, one record per employee-day) and its audit
 * trail apply unchanged. The note is recorded in that audit entry.
 */
export function RecordDecisionDialog({
  row,
  date,
  onClose,
}: {
  row: DailyReviewRow | null;
  /** The attendance day, `YYYY-MM-DD`. */
  date: string;
  onClose: () => void;
}) {
  const open = row !== null;
  const create = useCreateAttendance();
  const update = useUpdateAttendance(row?.attendance_record_id ?? "");

  const [status, setStatus] = React.useState<AttendanceStatus>("present");
  const [checkIn, setCheckIn] = React.useState("");
  const [checkOut, setCheckOut] = React.useState("");
  const [note, setNote] = React.useState("");

  // Seed the form when a row is opened. Existing decision first; otherwise the
  // biometric boundary, so the common case is "confirm what the device saw"
  // rather than "retype it".
  React.useEffect(() => {
    if (!row) return;
    setStatus((row.attendance_status as AttendanceStatus) ?? "present");
    setCheckIn(toTimeInput(row.attendance_check_in_at ?? row.first_in));
    setCheckOut(toTimeInput(row.attendance_check_out_at ?? row.last_out));
    // Seed the existing reason so re-opening a decided day shows what was
    // written rather than a blank box that would erase it on save.
    setNote(row.attendance_note ?? "");
  }, [row]);

  const pending = create.isPending || update.isPending;

  async function onSave() {
    if (!row) return;
    const body = {
      status,
      check_in_at: toInstant(date, checkIn),
      check_out_at: toInstant(date, checkOut),
      note: note.trim() || null,
    };
    try {
      if (row.attendance_record_id) {
        await update.mutateAsync(body);
      } else {
        await create.mutateAsync({
          employee_id: row.employee_id,
          attendance_date: date,
          ...body,
        });
      }
      toast.success(`${row.employee_name ?? "Record"} saved`);
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save the record.");
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-base">
            {row?.employee_name ?? "Attendance"}
          </DialogTitle>
        </DialogHeader>

        {row && (
          <div className="space-y-4">
            {/* Evidence. Read-only, and labelled as such - a PM must be able to
                see what the device recorded while deciding what it meant. */}
            <div className="rounded-lg border border-border bg-secondary/40 p-3">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Biometric evidence
              </p>
              <div className="mt-2 grid grid-cols-3 gap-2 text-sm">
                <Evidence label="First IN" value={timeOrDash(row.first_in)} />
                <Evidence label="Last OUT" value={timeOrDash(row.last_out)} />
                <Evidence
                  label="Worked"
                  value={formatWorked(row.worked_minutes)}
                  muted={row.worked_minutes == null}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="decision-status">Attendance status</Label>
              <Select
                value={status}
                onValueChange={(v) => setStatus(v as AttendanceStatus)}
              >
                <SelectTrigger id="decision-status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ATTENDANCE_STATUSES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {ATTENDANCE_STATUS_LABEL[s]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* A time the device recorded is evidence and is not editable. Only
                a boundary the device MISSED can be supplied by hand - that is
                the whole point of a manual entry here. */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="decision-in">Check in</Label>
                <Input
                  id="decision-in"
                  type="time"
                  value={checkIn}
                  disabled={!row.can_set_check_in}
                  onChange={(e) => setCheckIn(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="decision-out">Check out</Label>
                <Input
                  id="decision-out"
                  type="time"
                  value={checkOut}
                  disabled={!row.can_set_check_out}
                  onChange={(e) => setCheckOut(e.target.value)}
                />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              {row.can_set_check_in || row.can_set_check_out
                ? "The device did not record one of these. Enter the real time."
                : "Both punches came from the device and cannot be edited."}
            </p>

            <div className="space-y-1.5">
              <Label htmlFor="decision-note">Reason</Label>
              <Textarea
                id="decision-note"
                rows={2}
                placeholder="Why this day was set this way"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                maxLength={500}
              />
              <p className="text-xs text-muted-foreground">
                Recorded in the audit trail with your name and the time.
              </p>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="secondary" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button onClick={() => void onSave()} disabled={pending}>
            {pending ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Evidence({
  label,
  value,
  muted,
}: {
  label: string;
  value: string;
  muted?: boolean;
}) {
  return (
    <div>
      <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className={`tabular mt-0.5 font-semibold ${muted ? "text-muted-foreground" : ""}`}>
        {value}
      </p>
    </div>
  );
}

function timeOrDash(iso: string | null): string {
  return iso ? formatISTTime(iso) : "-";
}

/** An ISO instant as `HH:MM` for a `<input type="time">`, in office time.
 *
 *  Deliberately NOT `formatISTTime`: that renders the 12-hour clock the UI
 *  displays ("05:30 PM"), which a time input rejects outright and silently
 *  blanks. The input is a machine value; only what a person reads is 12-hour. */
function toTimeInput(iso: string | null): string {
  return istTimeInputValue(iso);
}

/**
 * `"2026-08-10"` + `"09:13"` -> an ISO instant at that Asia/Kolkata wall clock.
 *
 * The offset is written explicitly rather than letting the browser interpret the
 * string in its own zone: a PM working from a different timezone must still be
 * recording 09:13 IST, which is what the office and the device mean.
 */
function toInstant(date: string, time: string): string | null {
  if (!/^\d{2}:\d{2}$/.test(time)) return null;
  return `${date}T${time}:00+05:30`;
}
