"use client";

import * as React from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { CalendarClock, CircleCheck, Info, TriangleAlert } from "lucide-react";

import { ErrorState } from "@/components/feedback/error-state";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import { BackButton } from "@/components/shell/back-button";
import { PageHeader } from "@/components/shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Combobox } from "@/components/ui/combobox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { istTodayISO } from "@/lib/ist";
import { cn } from "@/lib/utils";
import { biometricKeys } from "@/features/biometric/keys";
import { useCalendarEvents } from "@/features/calendar/hooks";
import { leaveBalanceKeys } from "@/features/leave-balances/keys";

import { attendanceApi } from "../api";
import {
  MAX_BULK_DATES,
  MAX_BULK_EMPLOYEES,
  MAX_NOTE_LEN,
  OUTCOME_LABEL,
  OUTCOME_VARIANT,
  VERDICT_TEXT,
  applyVerdict,
  changedSincePreview,
  createApplyOnce,
  datesInRange,
  formatBulkDate,
  futureDates,
  futureWorkedNotice,
  isIsoDate,
  leaveBlockingRows,
  nonWorkingReason,
  planRangeDates,
  previewBody,
  reasonRequired,
  runPreview,
  tallyResults,
  validateDraft,
  type BulkDraft,
  type BulkMode,
  type RunOutcome,
  type Tally,
} from "../bulk-apply";
import { FUTURE_DATE_NOTICE } from "../date-rules";
import { calendarDayMaps } from "../day-status";
import { useEmployeeOptions } from "../employee-options";
import { useAttendanceSheet } from "../hooks";
import { attendanceKeys } from "../keys";
import { ATTENDANCE_STATUSES, ATTENDANCE_STATUS_LABEL } from "../schemas";
import type {
  AttendanceBulkApplyBody,
  AttendanceBulkApplyItem,
  AttendanceBulkApplyResult,
  AttendanceStatus,
} from "../types";

type Step = "configure" | "preview" | "confirm" | "results";

const STEPS: { key: Step; label: string }[] = [
  { key: "configure", label: "Configure" },
  { key: "preview", label: "Preview" },
  { key: "confirm", label: "Confirm" },
  { key: "results", label: "Results" },
];

const MODES: { value: BulkMode; label: string; hint: string }[] = [
  {
    value: "one-employee",
    label: "One employee, multiple dates",
    hint: "Set a status across a date range for one person.",
  },
  {
    value: "one-date",
    label: "Multiple employees, one date",
    hint: "Set a status for several people on the same day.",
  },
];

/** A successful preview: the exact request that was previewed and its answer. */
interface Preview {
  request: AttendanceBulkApplyBody;
  result: AttendanceBulkApplyResult;
}

/**
 * Bulk attendance - one status over many employee-days.
 *
 * CONFIGURE -> PREVIEW -> CONFIRM -> RESULTS, with no shortcut: the only way to
 * write is to confirm a preview the server produced. Everything the steps decide
 * lives in `bulk-apply.ts` (pure, unit-tested); this file renders it.
 *
 * Nothing here is kept in the URL or storage on purpose: a refresh or Back
 * lands on a fresh Configure step, so a save can never be resubmitted by
 * navigation. The server re-checks every row on apply and stays the authority
 * for permissions, the reason rule, leave protection and working days.
 */
export function BulkAttendance() {
  const queryClient = useQueryClient();
  const today = React.useMemo(() => istTodayISO(), []);

  const [step, setStep] = React.useState<Step>("configure");
  const [mode, setMode] = React.useState<BulkMode>("one-employee");

  // Mode A
  const [employeeId, setEmployeeId] = React.useState("");
  const [from, setFrom] = React.useState("");
  const [to, setTo] = React.useState("");
  const [excludedDates, setExcludedDates] = React.useState<Set<string>>(new Set());

  // Mode B - selection order is kept, so results read in the order picked.
  const [date, setDate] = React.useState(today);
  const [selected, setSelected] = React.useState<string[]>([]);

  // Shared
  const [status, setStatus] = React.useState<AttendanceStatus | "">("");
  // Always starts empty: a retrospective change must explain itself, and no
  // reason stored on an existing record is ever offered as this one.
  const [note, setNote] = React.useState("");
  const [showErrors, setShowErrors] = React.useState(false);

  const [previewing, setPreviewing] = React.useState(false);
  const [previewError, setPreviewError] = React.useState<string | null>(null);
  const [preview, setPreview] = React.useState<Preview | null>(null);

  const applyOnce = React.useRef<ReturnType<typeof createApplyOnce> | null>(null);
  const [applying, setApplying] = React.useState(false);
  const [applied, setApplied] = React.useState<RunOutcome | null>(null);

  // â”€â”€ derived â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const range = React.useMemo(
    () => (mode === "one-employee" && from && to ? datesInRange(from, to) : null),
    [mode, from, to],
  );
  const rangeProblem =
    mode === "one-employee" && from && to && !range
      ? from > to
        ? "The end date must be on or after the start date."
        : "That range is too long. Choose a range of at most a year - and no more than 62 included dates."
      : null;
  const calFrom = mode === "one-employee" ? (range?.[0] ?? today) : isIsoDate(date) ? date : today;
  const calTo =
    mode === "one-employee" ? (range?.[range.length - 1] ?? today) : isIsoDate(date) ? date : today;
  const eventsQuery = useCalendarEvents({ from: calFrom, to: calTo, limit: 100 });
  const calendar = React.useMemo(
    () => calendarDayMaps(eventsQuery.data?.items ?? []),
    [eventsQuery.data],
  );

  const planned = React.useMemo(
    () =>
      range
        ? // Non-working days are never applied by a bulk update: they stay
          // listed with the reason they are skipped, but are never sent.
          planRangeDates({ dates: range, excluded: excludedDates, includeNonWorking: false, calendar })
        : [],
    [range, excludedDates, calendar],
  );
  const modeBNonWorking =
    mode === "one-date" && isIsoDate(date) ? nonWorkingReason(date, calendar) : null;

  const includedDates =
    mode === "one-employee"
      ? planned.filter((p) => p.included).map((p) => p.date)
      : isIsoDate(date)
        ? [date]
        : [];
  const employeeIds = mode === "one-employee" ? (employeeId ? [employeeId] : []) : selected;

  const draft: BulkDraft = {
    mode,
    employeeIds,
    dates: includedDates,
    status,
    note,
    includeNonWorking: false,
  };
  const errors = [
    ...(rangeProblem ? [rangeProblem] : []),
    ...(modeBNonWorking
      ? [
          `${formatBulkDate(date)} is a non-working day (${modeBNonWorking}). Bulk updates never apply to non-working days - choose a working day.`,
        ]
      : []),
    ...(mode === "one-employee" && (!from || !to) ? ["Pick a start and an end date."] : []),
    ...validateDraft(draft, today).filter(
      // The range message above already says what is wrong with the dates.
      (e) => !(mode === "one-employee" && (!from || !to || rangeProblem) && e.startsWith("No dates")),
    ),
  ];
  const needsReason = reasonRequired(includedDates, today);
  const anyFuture = futureDates(includedDates, today).length > 0;
  const worked = futureWorkedNotice(status, includedDates, today);

  // â”€â”€ actions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  async function onPreview() {
    setShowErrors(true);
    setPreviewError(null);
    if (errors.length > 0 || previewing) return;
    setPreviewing(true);
    const out = await runPreview(attendanceApi.bulkApply, previewBody(draft));
    setPreviewing(false);
    if (out.kind === "result") {
      setPreview({ request: out.request, result: out.result });
      setStep("preview");
    } else if (out.kind === "unverified") {
      setPreviewError(
        `The preview response could not be verified (${out.problem}) Nothing was saved - run the preview again.`,
      );
    } else {
      setPreviewError(out.error.message);
    }
  }

  function toConfirm() {
    // A fresh one-shot sender per confirmation: it can send once, ever.
    applyOnce.current = createApplyOnce(attendanceApi.bulkApply);
    setStep("confirm");
  }

  async function onApply() {
    const run = applyOnce.current;
    if (!preview || !run || applying) return;
    setApplying(true);
    const out = await run(preview.request);
    setApplying(false);
    if (out === null) return; // already sent once - never again
    setApplied(out);
    setStep("results");
    // Whatever the answer, the days may have changed (an ambiguous failure
    // included), so every screen reading them refetches.
    void queryClient.invalidateQueries({ queryKey: attendanceKeys.all });
    void queryClient.invalidateQueries({ queryKey: biometricKeys.all });
    void queryClient.invalidateQueries({ queryKey: leaveBalanceKeys.all });
  }

  function backToEdit() {
    // The preview answered a request that is about to change - drop it.
    setPreview(null);
    applyOnce.current = null;
    setApplied(null);
    setStep("configure");
  }

  function startOver() {
    setEmployeeId("");
    setFrom("");
    setTo("");
    setExcludedDates(new Set());
    setDate(today);
    setSelected([]);
    setStatus("");
    setNote("");
    setShowErrors(false);
    setPreviewError(null);
    backToEdit();
  }

  function changeMode(next: BulkMode) {
    setMode(next);
    setShowErrors(false);
    setPreviewError(null);
  }

  // Shared by both modes: the status sits in the mode's own selection row,
  // the date notices directly under it.
  const statusField = (
    <div className="space-y-1.5">
      <Label htmlFor="bulk-status">Attendance status</Label>
      <Select value={status} onValueChange={(v) => setStatus(v as AttendanceStatus)}>
        <SelectTrigger id="bulk-status" aria-invalid={showErrors && !status}>
          <SelectValue placeholder="Choose a status" />
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
  );

  const notices = (
    <>
      {anyFuture && (
        <Notice tone="info" icon={CalendarClock}>
          {FUTURE_DATE_NOTICE} Future days are planned by status only - no check-in or
          check-out is sent.
        </Notice>
      )}
      {worked && <Notice tone="warning">{worked}</Notice>}
    </>
  );

  // â”€â”€ render â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  return (
    <>
      <BackButton href="/attendance?tab=history" label="Attendance" />
      <PageHeader
        title="Bulk Attendance Update"
        subtitle="Set one attendance status for many employee-days. Preview, confirm, then review what was saved."
      />

      <StepIndicator current={step} />

      {step === "configure" && (
        <div className="space-y-5">
          <fieldset className="rounded-lg border border-border bg-card p-4">
            <legend className="px-1 text-sm font-semibold">Mode</legend>
            <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label="Bulk update mode">
              {MODES.map((m) => (
                <label
                  key={m.value}
                  className={cn(
                    "flex cursor-pointer items-start gap-2.5 rounded-lg border p-3",
                    mode === m.value ? "border-primary bg-accent/40" : "border-border",
                  )}
                >
                  <input
                    type="radio"
                    name="bulk-mode"
                    className="mt-0.5 h-4 w-4 accent-primary"
                    checked={mode === m.value}
                    onChange={() => changeMode(m.value)}
                  />
                  <span className="text-sm">
                    <span className="font-medium">{m.label}</span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">{m.hint}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          {mode === "one-employee" ? (
            <ModeAConfig
              employeeId={employeeId}
              onEmployee={setEmployeeId}
              from={from}
              to={to}
              onFrom={(v) => {
                setFrom(v);
                setExcludedDates(new Set());
              }}
              onTo={(v) => {
                setTo(v);
                setExcludedDates(new Set());
              }}
              statusField={statusField}
              notices={notices}
              planned={planned}
              includedCount={includedDates.length}
              today={today}
              onToggleDate={(d) =>
                setExcludedDates((prev) => {
                  const next = new Set(prev);
                  if (next.has(d)) next.delete(d);
                  else next.add(d);
                  return next;
                })
              }
            />
          ) : (
            <ModeBConfig
              date={date}
              onDate={setDate}
              today={today}
              selected={selected}
              onSelected={setSelected}
              nonWorking={modeBNonWorking}
              statusField={statusField}
              notices={notices}
            />
          )}

          <section className="space-y-4 rounded-lg border border-border bg-card p-4">
            <div className="space-y-1.5">
              <Label htmlFor="bulk-note">
                Reason{needsReason && <span className="text-destructive"> *</span>}
              </Label>
              <Textarea
                id="bulk-note"
                rows={2}
                maxLength={MAX_NOTE_LEN}
                placeholder="Why these days are being set this way"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                aria-required={needsReason}
                aria-invalid={showErrors && needsReason && note.trim() === ""}
              />
              <p className="text-xs text-muted-foreground">
                {needsReason
                  ? "Required: past dates are included. One reason covers the whole update and is recorded in the audit trail for every row it changes."
                  : "Optional for today and future dates. Recorded in the audit trail for every row it changes."}
              </p>
            </div>
          </section>

          {showErrors && errors.length > 0 && (
            <div
              role="alert"
              className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm"
            >
              <p className="font-medium text-destructive">Fix these before previewing:</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-foreground">
                {errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </div>
          )}
          {previewError && (
            <Notice tone="danger" role="alert">
              {previewError}
            </Notice>
          )}

          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button variant="secondary" asChild>
              <Link href="/attendance?tab=history">Cancel</Link>
            </Button>
            <Button onClick={() => void onPreview()} disabled={previewing}>
              {previewing ? "Previewing..." : "Preview changes"}
            </Button>
          </div>
        </div>
      )}

      {step === "preview" && preview && (
        <PreviewStep
          preview={preview}
          today={today}
          onBack={backToEdit}
          onContinue={toConfirm}
        />
      )}

      {step === "confirm" && preview && (
        <ConfirmStep
          preview={preview}
          mode={mode}
          today={today}
          applying={applying}
          onBack={() => {
            applyOnce.current = null;
            setStep("preview");
          }}
          onApply={() => void onApply()}
        />
      )}

      {step === "results" && applied && preview && (
        <ResultsStep
          outcome={applied}
          preview={preview}
          mode={mode}
          onEdit={backToEdit}
          onStartOver={startOver}
        />
      )}
    </>
  );
}

// â”€â”€â”€ configure: mode A â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function ModeAConfig({
  employeeId,
  onEmployee,
  from,
  to,
  onFrom,
  onTo,
  statusField,
  notices,
  planned,
  includedCount,
  today,
  onToggleDate,
}: {
  employeeId: string;
  onEmployee: (id: string) => void;
  from: string;
  to: string;
  onFrom: (v: string) => void;
  onTo: (v: string) => void;
  statusField: React.ReactNode;
  notices: React.ReactNode;
  planned: ReturnType<typeof planRangeDates>;
  includedCount: number;
  today: string;
  onToggleDate: (date: string) => void;
}) {
  const employees = useEmployeeOptions();
  const options = employees.items.map((e) => ({
    value: e.id,
    label: e.full_name,
    sublabel: e.employee_code,
    description: e.status !== "active" ? `Status: ${e.status}` : undefined,
  }));
  const skipped = planned.length - includedCount;

  return (
    <section className="space-y-4 rounded-lg border border-border bg-card p-4">
      <h2 className="text-sm font-semibold">Employee, dates and status</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-1.5">
          <Label>Employee</Label>
          <Combobox
            value={employeeId}
            onValueChange={onEmployee}
            options={options}
            placeholder={employees.isLoading ? "Loading employees..." : "Select an employee"}
            searchPlaceholder="Search by name or code"
            emptyMessage="No matching employees."
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="bulk-from">From</Label>
          <Input id="bulk-from" type="date" value={from} onChange={(e) => onFrom(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="bulk-to">To</Label>
          <Input id="bulk-to" type="date" value={to} min={from || undefined} onChange={(e) => onTo(e.target.value)} />
        </div>
        {statusField}
      </div>

      {notices}

      {planned.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm" aria-live="polite">
            <span className="font-medium">
              {includedCount} of {planned.length} date{planned.length === 1 ? "" : "s"} included
            </span>
            {skipped > 0 && (
              <span className="text-muted-foreground"> - {skipped} skipped or excluded, listed below with why.</span>
            )}
            {includedCount > MAX_BULK_DATES && (
              <span className="text-destructive"> One update can cover at most {MAX_BULK_DATES} dates.</span>
            )}
          </p>
          <ul
            className="max-h-72 divide-y divide-border overflow-y-auto rounded-md border border-border"
            aria-label="Dates in the range"
          >
            {planned.map((p) => {
              const id = `bulk-date-${p.date}`;
              const offAndSkipped = p.nonWorking !== null && !p.excludedByPm && !p.included;
              return (
                <li key={p.date} className="flex items-center gap-3 px-3 py-2 text-sm">
                  <Checkbox
                    id={id}
                    checked={!p.excludedByPm}
                    disabled={offAndSkipped}
                    onChange={() => onToggleDate(p.date)}
                    aria-describedby={p.skipNote ? `${id}-note` : undefined}
                  />
                  <label htmlFor={id} className={cn("min-w-0 flex-1", !p.included && "text-muted-foreground")}>
                    <span className="font-medium tabular">{formatBulkDate(p.date)}</span>
                    {p.date < today && <Badge variant="neutral" className="ml-2">Past</Badge>}
                    {p.date === today && <Badge variant="info" className="ml-2">Today</Badge>}
                    {p.date > today && <Badge variant="outline" className="ml-2">Future</Badge>}
                  </label>
                  {p.skipNote && (
                    <span id={`${id}-note`} className="shrink-0 text-xs text-muted-foreground">
                      {p.skipNote}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
          <p className="text-xs text-muted-foreground">
            Untick a date to leave it out. Non-working days (Sundays, the 2nd and 4th Saturday
            and company holidays) are always skipped; the server re-checks every date.
          </p>
        </div>
      )}
    </section>
  );
}

// â”€â”€â”€ configure: mode B â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function ModeBConfig({
  date,
  onDate,
  today,
  selected,
  onSelected,
  nonWorking,
  statusField,
  notices,
}: {
  date: string;
  onDate: (v: string) => void;
  today: string;
  selected: string[];
  onSelected: (ids: string[]) => void;
  nonWorking: string | null;
  statusField: React.ReactNode;
  notices: React.ReactNode;
}) {
  const validDate = isIsoDate(date);
  // The existing PM roster for the day: every active employee, with the status
  // already on record (or none). The same list the daily sheet is built from.
  const sheet = useAttendanceSheet(validDate ? date : undefined);
  const [q, setQ] = React.useState("");

  const rows = sheet.data?.rows ?? [];
  const needle = q.trim().toLowerCase();
  const shown = needle
    ? rows.filter(
        (r) =>
          r.employee_name.toLowerCase().includes(needle) ||
          r.employee_code.toLowerCase().includes(needle),
      )
    : rows;
  const selectedSet = new Set(selected);

  function toggle(id: string) {
    onSelected(selectedSet.has(id) ? selected.filter((s) => s !== id) : [...selected, id]);
  }
  function selectShown() {
    const add = shown.map((r) => r.employee_id).filter((id) => !selectedSet.has(id));
    onSelected([...selected, ...add]);
  }
  function clearShown() {
    const drop = new Set(shown.map((r) => r.employee_id));
    onSelected(selected.filter((id) => !drop.has(id)));
  }

  return (
    <section className="space-y-4 rounded-lg border border-border bg-card p-4">
      <h2 className="text-sm font-semibold">Date, status and employees</h2>
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label htmlFor="bulk-date">Attendance date</Label>
          <Input id="bulk-date" type="date" value={date} onChange={(e) => onDate(e.target.value)} />
          {validDate && (
            <p className="text-xs text-muted-foreground">
              {formatBulkDate(date)}
              {date < today ? " - past" : date === today ? " - today" : " - future"}
            </p>
          )}
        </div>
        {statusField}
        <div className="space-y-1.5">
          <Label htmlFor="bulk-search">Find employees</Label>
          <Input
            id="bulk-search"
            type="search"
            placeholder="Search by name or code"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>

      {nonWorking && (
        <Notice tone="warning">
          {formatBulkDate(date)} is a non-working day ({nonWorking}). Bulk updates never apply
          to non-working days - choose a working day.
        </Notice>
      )}
      {notices}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm" aria-live="polite">
          <span className="font-medium">{selected.length}</span> of {rows.length} employee
          {rows.length === 1 ? "" : "s"} selected
          {selected.length > MAX_BULK_EMPLOYEES && (
            <span className="text-destructive"> - at most {MAX_BULK_EMPLOYEES} per update.</span>
          )}
        </p>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={selectShown} disabled={shown.length === 0}>
            Select {needle ? "shown" : "all"}
          </Button>
          <Button variant="secondary" size="sm" onClick={clearShown} disabled={selected.length === 0}>
            Clear {needle ? "shown" : "all"}
          </Button>
        </div>
      </div>

      <div className="max-h-96 overflow-y-auto rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <span className="sr-only">Include</span>
              </TableHead>
              <TableHead>Employee</TableHead>
              <TableHead className="w-40">Current status</TableHead>
            </TableRow>
          </TableHeader>
          {sheet.isLoading && <TableSkeleton cols={3} />}
          {!sheet.isLoading && !sheet.isError && (
            <TableBody>
              {shown.map((r) => {
                const id = `bulk-emp-${r.employee_id}`;
                return (
                  <TableRow key={r.employee_id}>
                    <TableCell>
                      <Checkbox
                        id={id}
                        checked={selectedSet.has(r.employee_id)}
                        onChange={() => toggle(r.employee_id)}
                      />
                    </TableCell>
                    <TableCell>
                      <label htmlFor={id} className="cursor-pointer font-medium">
                        {r.employee_name}
                        <span className="ml-1.5 text-xs font-normal text-muted-foreground">
                          {r.employee_code}
                        </span>
                      </label>
                    </TableCell>
                    <TableCell className="text-sm">
                      {/* The sheet defaults an unrecorded day to Present; say
                          "No record" instead so it is not read as a decision. */}
                      {r.record_id ? (
                        <Badge variant="outline">{ATTENDANCE_STATUS_LABEL[r.status]}</Badge>
                      ) : (
                        <span className="text-muted-foreground">No record</span>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          )}
        </Table>
        {!validDate && (
          <p className="p-4 text-sm text-muted-foreground">Pick a date to load the roster.</p>
        )}
        {sheet.isError && (
          <ErrorState message="Could not load employees for this date." onRetry={() => void sheet.refetch()} />
        )}
        {validDate && !sheet.isLoading && !sheet.isError && shown.length === 0 && (
          <p className="p-4 text-sm text-muted-foreground">
            {needle ? "No employees match this search." : "No active employees."}
          </p>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        Untick an employee to leave them out. Selections are kept while you search.
      </p>
    </section>
  );
}

// â”€â”€â”€ preview â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function PreviewStep({
  preview,
  today,
  onBack,
  onContinue,
}: {
  preview: Preview;
  today: string;
  onBack: () => void;
  onContinue: () => void;
}) {
  const rows = preview.result.results;
  const tally = tallyResults(rows);
  const blocked = leaveBlockingRows(rows);
  const worked = futureWorkedNotice(preview.request.status, preview.request.dates, today);
  const [attentionOnly, setAttentionOnly] = React.useState(false);

  return (
    <div className="space-y-4">
      <Notice tone="info" icon={Info}>
        Preview only - nothing has been saved. The server checked each row against today&apos;s
        records; it checks them again when you save, so the final result can differ.
      </Notice>

      <TallyStrip tally={tally} phase="preview" />

      {worked && <Notice tone="warning">{worked}</Notice>}
      {blocked.length > 0 && (
        <Notice tone="warning">
          {blocked.length} row{blocked.length === 1 ? " is" : "s are"} covered by a pending leave
          request. Saving {ATTENDANCE_STATUS_LABEL[preview.request.status]} there blocks that
          request&apos;s approval. Those rows are marked below; the status you chose is not changed.
        </Notice>
      )}

      <ResultTable
        rows={rows}
        requested={preview.request.status}
        phase="preview"
        attentionOnly={attentionOnly}
        onAttentionOnly={setAttentionOnly}
      />

      <div className="flex flex-wrap items-center justify-end gap-2">
        {tally.changed === 0 && (
          <p className="mr-auto text-sm text-muted-foreground">
            No row would change, so there is nothing to save. Go back to adjust the selection.
          </p>
        )}
        <Button variant="secondary" onClick={onBack}>
          Back to edit
        </Button>
        <Button onClick={onContinue} disabled={tally.changed === 0}>
          Continue to confirm
        </Button>
      </div>
    </div>
  );
}

// â”€â”€â”€ confirm â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function ConfirmStep({
  preview,
  mode,
  today,
  applying,
  onBack,
  onApply,
}: {
  preview: Preview;
  mode: BulkMode;
  today: string;
  applying: boolean;
  onBack: () => void;
  onApply: () => void;
}) {
  const { request, result } = preview;
  const tally = tallyResults(result.results);
  const blocked = leaveBlockingRows(result.results);
  const worked = futureWorkedNotice(request.status, request.dates, today);
  const statusLabel = ATTENDANCE_STATUS_LABEL[request.status];
  const first = result.results[0];

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 text-sm font-semibold">Confirm bulk update</h2>
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[max-content_1fr]">
          <dt className="text-muted-foreground">{mode === "one-employee" ? "Employee" : "Employees"}</dt>
          <dd>
            {mode === "one-employee"
              ? employeeLabel(first)
              : `${request.employee_ids.length} employee${request.employee_ids.length === 1 ? "" : "s"}`}
          </dd>
          <dt className="text-muted-foreground">{request.dates.length === 1 ? "Date" : "Dates"}</dt>
          <dd>{datesLabel(request.dates)}</dd>
          <dt className="text-muted-foreground">Status</dt>
          <dd>
            All {tally.total} employee-day{tally.total === 1 ? "" : "s"} requested as{" "}
            <span className="font-medium">{statusLabel}</span>
          </dd>
          <dt className="text-muted-foreground">Will be saved (per preview)</dt>
          <dd>
            <span className="font-medium">{tally.changed}</span> ({tally.created} new, {tally.updated} changed)
          </dd>
          <dt className="text-muted-foreground">Already set</dt>
          <dd>{tally.unchanged}</dd>
          <dt className="text-muted-foreground">Will not be saved</dt>
          <dd>
            {tally.refused} ({tally.rejected} rejected, {tally.protected} protected by leave)
          </dd>
          <dt className="text-muted-foreground">Reason</dt>
          <dd className="whitespace-pre-wrap">{request.note ?? <span className="text-muted-foreground">None</span>}</dd>
        </dl>
      </section>

      {worked && <Notice tone="warning">{worked}</Notice>}
      {blocked.length > 0 && (
        <Notice tone="warning">
          {blocked.length} row{blocked.length === 1 ? " is" : "s are"} covered by a pending leave
          request; saving blocks {blocked.length === 1 ? "its" : "their"} approval.
        </Notice>
      )}

      <Notice tone="info" icon={Info}>
        Saving writes these records now. The server re-checks every row as it saves, so a row can
        still be refused if something changed since the preview - the results page shows exactly
        what happened to each one.
      </Notice>

      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button variant="secondary" onClick={onBack} disabled={applying}>
          Back to preview
        </Button>
        <Button onClick={onApply} disabled={applying} aria-busy={applying}>
          {applying
            ? "Saving..."
            : `Save ${tally.changed} record${tally.changed === 1 ? "" : "s"}`}
        </Button>
      </div>
    </div>
  );
}

// â”€â”€â”€ results â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function ResultsStep({
  outcome,
  preview,
  mode,
  onEdit,
  onStartOver,
}: {
  outcome: RunOutcome;
  preview: Preview;
  mode: BulkMode;
  onEdit: () => void;
  onStartOver: () => void;
}) {
  const [attentionOnly, setAttentionOnly] = React.useState(false);
  const recordsHref =
    mode === "one-date"
      ? `/attendance?tab=history&date=${preview.request.dates[0]}`
      : "/attendance?tab=history";

  const actions = (canEdit: boolean) => (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <Button variant="secondary" asChild>
        <Link href={recordsHref}>Go to Records</Link>
      </Button>
      {canEdit && (
        <Button variant="secondary" onClick={onEdit}>
          Back to edit
        </Button>
      )}
      <Button onClick={onStartOver}>Start a new bulk update</Button>
    </div>
  );

  if (outcome.kind === "error") {
    return (
      <div className="space-y-4">
        <Notice tone="danger" role="alert">
          <span className="font-medium">
            {outcome.error.ambiguous ? "The save result is unknown." : "Nothing was saved."}
          </span>{" "}
          {outcome.error.message}
        </Notice>
        {actions(!outcome.error.ambiguous)}
      </div>
    );
  }
  if (outcome.kind === "unverified") {
    return (
      <div className="space-y-4">
        <Notice tone="danger" role="alert">
          <span className="font-medium">The save result could not be verified.</span> The server
          answered, but its response was incomplete ({outcome.problem}) No row is shown as saved.
          Some or all records may have been saved - check the days on the Records tab before
          running this again.
        </Notice>
        {actions(false)}
      </div>
    );
  }

  const rows = outcome.result.results;
  const tally = tallyResults(rows);
  const verdict = applyVerdict(tally);
  const drift = changedSincePreview(preview.result.results, rows);

  return (
    <div className="space-y-4">
      <Notice
        tone={verdict === "all_saved" ? "success" : verdict === "nothing_to_change" ? "info" : "warning"}
        role="status"
      >
        <span className="font-medium">{VERDICT_TEXT[verdict]}</span>{" "}
        {tally.changed} of {tally.total} employee-day{tally.total === 1 ? "" : "s"} saved.
      </Notice>

      <TallyStrip tally={tally} phase="applied" />

      {drift > 0 && (
        <Notice tone="warning">
          {drift} row{drift === 1 ? "" : "s"} came out differently from the preview - the records
          changed between preview and save. The table shows the final result.
        </Notice>
      )}

      <ResultTable
        rows={rows}
        requested={outcome.result.status}
        phase="applied"
        attentionOnly={attentionOnly}
        onAttentionOnly={setAttentionOnly}
      />

      {actions(false)}
    </div>
  );
}

// â”€â”€â”€ shared pieces â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function StepIndicator({ current }: { current: Step }) {
  const index = STEPS.findIndex((s) => s.key === current);
  return (
    <ol className="mb-5 flex flex-wrap items-center gap-2 text-sm" aria-label="Progress">
      {STEPS.map((s, i) => (
        <li key={s.key} className="flex items-center gap-2" aria-current={i === index ? "step" : undefined}>
          <span
            className={cn(
              "flex h-6 w-6 items-center justify-center rounded-full border text-xs font-semibold",
              i === index
                ? "border-primary bg-primary text-primary-foreground"
                : i < index
                  ? "border-primary text-primary"
                  : "border-border text-muted-foreground",
            )}
          >
            {i + 1}
          </span>
          <span className={cn(i === index ? "font-medium" : "text-muted-foreground")}>{s.label}</span>
          {i < STEPS.length - 1 && <span className="mx-1 h-px w-6 bg-border" aria-hidden />}
        </li>
      ))}
    </ol>
  );
}

function TallyStrip({ tally, phase }: { tally: Tally; phase: "preview" | "applied" }) {
  const label = OUTCOME_LABEL[phase];
  const items: [string, number, string?][] = [
    [phase === "preview" ? "Rows reviewed" : "Rows processed", tally.total],
    [phase === "preview" ? "Eligible to save" : "Saved", tally.changed, "text-success"],
    [label.unchanged, tally.unchanged],
    [label.protected, tally.protected, tally.protected ? "text-warning" : undefined],
    [label.rejected, tally.rejected, tally.rejected ? "text-destructive" : undefined],
  ];
  return (
    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-5">
      {items.map(([name, value, tone]) => (
        <div key={name} className="rounded-lg border border-border bg-card px-3 py-2">
          <dt className="text-xs text-muted-foreground">{name}</dt>
          <dd className={cn("tabular text-lg font-semibold", tone)}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function needsAttention(r: AttendanceBulkApplyItem): boolean {
  return r.outcome === "rejected" || r.outcome === "protected" || (r.warnings ?? []).length > 0;
}

function ResultTable({
  rows,
  requested,
  phase,
  attentionOnly,
  onAttentionOnly,
}: {
  rows: AttendanceBulkApplyItem[];
  requested: AttendanceStatus;
  phase: "preview" | "applied";
  attentionOnly: boolean;
  onAttentionOnly: (v: boolean) => void;
}) {
  const attention = rows.filter(needsAttention).length;
  const shown = attentionOnly ? rows.filter(needsAttention) : rows;
  const label = OUTCOME_LABEL[phase];

  return (
    <div className="space-y-2">
      <label className="inline-flex cursor-pointer items-center gap-2 text-sm">
        <Checkbox
          checked={attentionOnly}
          onChange={(e) => onAttentionOnly(e.target.checked)}
          disabled={attention === 0}
        />
        Show only rows needing attention ({attention})
      </label>
      <div className="max-h-[32rem] overflow-y-auto rounded-lg border border-border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Employee</TableHead>
              <TableHead className="w-36">Date</TableHead>
              <TableHead className="w-28">Current</TableHead>
              <TableHead className="w-28">Requested</TableHead>
              <TableHead className="w-40">Outcome</TableHead>
              <TableHead>Details</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.map((r) => (
              <TableRow
                key={`${r.employee_id}|${r.attendance_date}`}
                className={cn(r.outcome === "rejected" && "bg-destructive/5", r.outcome === "protected" && "bg-warning/5")}
              >
                <TableCell className="font-medium">{employeeLabel(r)}</TableCell>
                <TableCell className="tabular">{formatBulkDate(r.attendance_date)}</TableCell>
                <TableCell className="text-sm">{currentLabel(r)}</TableCell>
                <TableCell className="text-sm">{ATTENDANCE_STATUS_LABEL[requested]}</TableCell>
                <TableCell>
                  <Badge variant={OUTCOME_VARIANT[r.outcome]} dot>
                    {label[r.outcome]}
                  </Badge>
                </TableCell>
                <TableCell className="text-sm">
                  {r.message && <p className="text-muted-foreground">{r.message}</p>}
                  {(r.warnings ?? []).map((w) => (
                    <p key={w.code} className="mt-0.5 flex items-start gap-1 text-warning">
                      <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                      {w.message}
                    </p>
                  ))}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {shown.length === 0 && (
          <p className="p-4 text-sm text-muted-foreground">No rows need attention.</p>
        )}
      </div>
    </div>
  );
}

function employeeLabel(r: AttendanceBulkApplyItem | undefined): string {
  if (!r) return "-";
  if (!r.employee_name) return "Unknown employee";
  return r.employee_code ? `${r.employee_name} (${r.employee_code})` : r.employee_name;
}

/** The day's status before the action, where the server knows it. */
function currentLabel(r: AttendanceBulkApplyItem): string {
  if (r.previous_status) return ATTENDANCE_STATUS_LABEL[r.previous_status];
  if (r.outcome === "created") return "No record";
  return "-";
}

function datesLabel(dates: readonly string[]): string {
  if (dates.length === 1) return formatBulkDate(dates[0]);
  return `${formatBulkDate(dates[0])} to ${formatBulkDate(dates[dates.length - 1])} (${dates.length} dates)`;
}

const NOTICE_TONE = {
  info: "border-border bg-secondary/40 text-foreground",
  success: "border-success/30 bg-success/10 text-foreground",
  warning: "border-warning/30 bg-warning/10 text-foreground",
  danger: "border-destructive/30 bg-destructive/5 text-foreground",
} as const;

function Notice({
  tone,
  icon: Icon = TriangleAlert,
  role,
  children,
}: {
  tone: keyof typeof NOTICE_TONE;
  icon?: React.ComponentType<{ className?: string }>;
  role?: "alert" | "status";
  children: React.ReactNode;
}) {
  return (
    <div role={role} className={cn("flex items-start gap-2 rounded-lg border p-3 text-sm", NOTICE_TONE[tone])}>
      {/* Success gets a check, never the caution triangle. */}
      {tone === "success" ? (
        <CircleCheck className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden />
      ) : (
        <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
      )}
      <div>{children}</div>
    </div>
  );
}
