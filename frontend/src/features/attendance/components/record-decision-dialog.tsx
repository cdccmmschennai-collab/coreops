"use client";

import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
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
import { istTodayISO } from "@/lib/ist";
import {
  formatISTTime,
  istTimeInputValue,
} from "@/features/biometric/mapping-format";
import { formatWorked } from "@/features/biometric/review";
import type { DailyReviewRow } from "@/features/biometric/types";
import { usePermissionBalance } from "@/features/permissions/hooks";
import { permissionKeys } from "@/features/permissions/keys";
import {
  PERMISSION_PERIOD_HOURS,
  PERMISSION_PERIOD_LABEL,
  PERMISSION_PERIOD_OPTIONS,
  formatDuration,
  formatHours,
  isDurationAffordable,
  type PermissionPeriod,
} from "@/features/permissions/types";

import {
  FUTURE_TIMES_NOTICE,
  REASON_REQUIRED_MESSAGE,
  isFutureDate,
  isPastDate,
  isReasonMissing,
} from "../date-rules";
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
  // Whether the OTHER half of a half day came out of the leave balance. Only a
  // `half_day` can be ambiguous - a `leave` row is a whole day and a worked day
  // is none - so this is the only status that asks.
  const [chargesLeave, setChargesLeave] = React.useState(false);
  // The day's permission. `NO_PERMISSION` is the default for everyone;
  // `LEGACY_PERMISSION` stands for a permission filed before the four options
  // existed, which cannot be shown as one of them.
  const [permission, setPermission] = React.useState<PermissionChoice>(NO_PERMISSION);
  const [seededPermission, setSeededPermission] =
    React.useState<PermissionChoice>(NO_PERMISSION);

  const queryClient = useQueryClient();
  // The employee's allowance for the month of this day - what the selector
  // greys options out against. A convenience only: the save is re-checked
  // server-side under a lock, by the same rule a request approval uses.
  const balanceQuery = usePermissionBalance(row?.employee_id, date, { enabled: open });

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
    // Unticked unless this day already says it charged leave. A day that never
    // stated a fraction (every row written before migration 0083, including the
    // company-wide half day) opens as "no leave", which is exactly what it has
    // always been worth - re-saving one cannot silently start billing it.
    setChargesLeave((row.attendance_leave_day_fraction ?? 0) > 0);
    const seeded = seedPermission(row);
    setPermission(seeded);
    setSeededPermission(seeded);
  }, [row]);

  const pending = create.isPending || update.isPending;

  // Where the day sits decides two rules, both also enforced by the backend: a
  // past day is a correction and needs a reason, a future day is planned by
  // status only. Read once per render from the IST calendar.
  const today = istTodayISO();
  const future = isFutureDate(date, today);
  const pastDay = isPastDate(date, today);
  const reasonMissing = isReasonMissing(date, note, today);

  // The hours this day already holds are given back if the PM picks another
  // option, so they count as available for the choice.
  const heldHours = row?.permission_hours ?? 0;
  const available = balanceQuery.data ? balanceQuery.data.remaining_hours + heldHours : null;
  const exhausted = available !== null && available < 1;

  async function onSave() {
    if (!row || reasonMissing) return;
    const body = {
      status,
      check_in_at: future ? null : toInstant(date, checkIn),
      check_out_at: future ? null : toInstant(date, checkOut),
      note: note.trim() || null,
      // Sent for every save, so unticking the box CLEARS the charge rather than
      // leaving the previous fraction behind. `null` on a non-half day means
      // "priced by status alone", which is what a Leave or a Present day is.
      leave_day_fraction: status === "half_day" ? (chargesLeave ? 0.5 : 0) : null,
      // Sent ONLY when the PM changed the selector. Omitted, the day's
      // permission is left exactly as it is - so re-saving a status, or a day
      // with a pending request, never touches the permission ledger.
      ...(permission !== seededPermission && permission !== LEGACY_PERMISSION
        ? { permission_period: permission === NO_PERMISSION ? null : permission }
        : {}),
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
      // The ledger, balance KPI and history all read the permission root.
      void queryClient.invalidateQueries({ queryKey: permissionKeys.all });
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

            {/* An ATTRIBUTE beside the status, never a status of its own. The
                four options are the request flow's own, and a choice is saved
                into the same permission ledger an approved request is. */}
            <div className="space-y-1.5">
              <Label htmlFor="decision-permission">Permission</Label>
              <Select
                value={permission}
                onValueChange={(v) => setPermission(v as PermissionChoice)}
              >
                <SelectTrigger id="decision-permission">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_PERMISSION}>No Permission</SelectItem>
                  {seededPermission === LEGACY_PERMISSION && (
                    <SelectItem value={LEGACY_PERMISSION} disabled>
                      {formatDuration(heldHours)} (recorded earlier)
                    </SelectItem>
                  )}
                  {PERMISSION_PERIOD_OPTIONS.map((p) => (
                    <SelectItem
                      key={p}
                      value={p}
                      disabled={
                        available !== null &&
                        p !== seededPermission &&
                        !isDurationAffordable(PERMISSION_PERIOD_HOURS[p], available)
                      }
                    >
                      {PERMISSION_PERIOD_LABEL[p]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {balanceQuery.data && (
                <p
                  className={`text-xs ${exhausted ? "text-warning" : "text-muted-foreground"}`}
                >
                  {exhausted
                    ? `Monthly permission allowance exhausted - all ${formatHours(
                        balanceQuery.data.allowance_hours,
                      )} used.`
                    : `${formatHours(balanceQuery.data.remaining_hours)} of ${formatHours(
                        balanceQuery.data.allowance_hours,
                      )} available this month.`}
                </p>
              )}
            </div>

            {/* The half a day a half day does not account for. `half_day` says
                the employee worked half the day and nothing about the rest, and
                the two possible rests cost completely different things:

                  ticked    a half-day LEAVE  - 0.5 comes off the balance
                  unticked  the office shut, or the half is unpaid - costs 0

                Asked rather than assumed, because nothing in the row can tell
                them apart and guessing either way is wrong for the other. */}
            {status === "half_day" && (
              <label
                htmlFor="decision-charges-leave"
                className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-border bg-secondary/40 p-3"
              >
                <input
                  id="decision-charges-leave"
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 shrink-0 accent-primary"
                  checked={chargesLeave}
                  onChange={(e) => setChargesLeave(e.target.checked)}
                />
                <span className="text-sm">
                  <span className="font-medium">Half-day leave</span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    Deducts 0.5 from the leave balance. Leave this unticked for a
                    company half day, which costs the employee nothing.
                  </span>
                </span>
              </label>
            )}

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
                  disabled={future || !row.can_set_check_in}
                  onChange={(e) => setCheckIn(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="decision-out">Check out</Label>
                <Input
                  id="decision-out"
                  type="time"
                  value={checkOut}
                  disabled={future || !row.can_set_check_out}
                  onChange={(e) => setCheckOut(e.target.value)}
                />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              {future
                ? FUTURE_TIMES_NOTICE
                : row.can_set_check_in || row.can_set_check_out
                  ? "The device did not record one of these. Enter the real time."
                  : "Both punches came from the device and cannot be edited."}
            </p>

            <div className="space-y-1.5">
              <Label htmlFor="decision-note">
                Reason
                {pastDay && <span className="text-destructive"> *</span>}
              </Label>
              <Textarea
                id="decision-note"
                rows={2}
                placeholder="Why this day was set this way"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                maxLength={500}
                aria-required={pastDay}
                aria-invalid={reasonMissing}
              />
              <p className="text-xs text-muted-foreground">
                {pastDay
                  ? `${REASON_REQUIRED_MESSAGE} It is recorded in the audit trail with your name and the time.`
                  : "Recorded in the audit trail with your name and the time."}
              </p>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="secondary" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button onClick={() => void onSave()} disabled={pending || reasonMissing}>
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

const NO_PERMISSION = "none";
const LEGACY_PERMISSION = "legacy";
type PermissionChoice = PermissionPeriod | typeof NO_PERMISSION | typeof LEGACY_PERMISSION;

/** What the selector opens on: the option this day already holds, else
 *  "No Permission". */
function seedPermission(row: DailyReviewRow): PermissionChoice {
  const period = row.permission_period;
  if (period && (PERMISSION_PERIOD_OPTIONS as readonly string[]).includes(period)) {
    return period as PermissionPeriod;
  }
  return row.permission_hours != null ? LEGACY_PERMISSION : NO_PERMISSION;
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
