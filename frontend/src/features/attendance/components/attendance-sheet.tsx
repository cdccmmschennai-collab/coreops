"use client";

import * as React from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
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
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import { AppError } from "@/lib/api-client";
import { istTodayISO } from "@/lib/ist";

import { useAttendanceSheet, useBulkSaveAttendance } from "../hooks";
import {
  ATTENDANCE_STATUSES,
  ATTENDANCE_STATUS_LABEL,
} from "../schemas";
import type { AttendanceSheet as AttendanceSheetData, AttendanceStatus } from "../types";

interface SheetRow {
  employee_id: string;
  employee_code: string;
  employee_name: string;
  status: AttendanceStatus;
}

interface SheetForm {
  rows: SheetRow[];
}

// Statuses offered by the "Mark selected …" bulk actions (existing statuses only).
const BULK_ACTIONS: AttendanceStatus[] = ["present", "absent", "leave", "half_day"];

function toRows(sheet: AttendanceSheetData | undefined): SheetRow[] {
  return (sheet?.rows ?? []).map((r) => ({
    employee_id: r.employee_id,
    employee_code: r.employee_code,
    employee_name: r.employee_name,
    status: r.status,
  }));
}

/** Header "select all" checkbox with an indeterminate state for partial selections. */
function SelectAllCheckbox({
  checked,
  indeterminate,
  onChange,
  disabled,
}: {
  checked: boolean;
  indeterminate: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  const ref = React.useRef<HTMLInputElement>(null);
  React.useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate && !checked;
  }, [indeterminate, checked]);
  return (
    <Checkbox
      ref={ref}
      checked={checked}
      disabled={disabled}
      aria-label="Select all employees"
      onChange={(e) => onChange(e.target.checked)}
    />
  );
}

/** Bulk attendance roster for a date (PM workflow). Loads the day's sheet —
 * every active employee, defaulting to present where nothing is saved yet —
 * and saves all rows in a single request. */
export function AttendanceSheet() {
  const [date, setDate] = React.useState(istTodayISO());
  const [search, setSearch] = React.useState("");
  // Selection persists across search/filter, keyed by employee_id.
  const [selected, setSelected] = React.useState<Record<string, boolean>>({});

  const query = useAttendanceSheet(date);
  const saveMutation = useBulkSaveAttendance();

  const { control, handleSubmit, reset, setValue, watch, formState } = useForm<SheetForm>({
    defaultValues: { rows: [] },
  });
  const { fields } = useFieldArray({ control, name: "rows" });
  const rows = watch("rows");

  // Seed the form whenever a freshly-fetched sheet arrives, and clear selection.
  const loadedKey = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!query.data) return;
    const key = `${query.data.attendance_date}:${query.dataUpdatedAt}`;
    if (loadedKey.current === key) return;
    loadedKey.current = key;
    reset({ rows: toRows(query.data) });
    setSelected({});
  }, [query.data, query.dataUpdatedAt, reset]);

  // Warn before leaving (reload / close tab) with unsaved edits.
  React.useEffect(() => {
    if (!formState.isDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [formState.isDirty]);

  function onDateChange(next: string) {
    if (!next || next === date) return;
    if (formState.isDirty && !window.confirm("Discard unsaved attendance changes?")) {
      return;
    }
    setDate(next);
  }

  // employee_id -> form row index, for selection-driven bulk edits.
  const indexById = React.useMemo(() => {
    const m = new Map<string, number>();
    fields.forEach((f, i) => m.set(f.employee_id, i));
    return m;
  }, [fields]);

  const visibleIndexes = React.useMemo(() => {
    const q = search.trim().toLowerCase();
    return fields
      .map((_, i) => i)
      .filter((i) => {
        if (!q) return true;
        const r = rows[i];
        if (!r) return true;
        return (
          r.employee_name.toLowerCase().includes(q) ||
          r.employee_code.toLowerCase().includes(q)
        );
      });
  }, [fields, rows, search]);

  const visibleIds = visibleIndexes.map((i) => fields[i].employee_id);
  const allVisibleSelected =
    visibleIds.length > 0 && visibleIds.every((id) => selected[id]);
  const someVisibleSelected = visibleIds.some((id) => selected[id]);
  const selectedCount = Object.values(selected).filter(Boolean).length;

  function toggleAllVisible(checked: boolean) {
    setSelected((prev) => {
      const next = { ...prev };
      for (const id of visibleIds) next[id] = checked;
      return next;
    });
  }

  function toggleOne(id: string, checked: boolean) {
    setSelected((prev) => ({ ...prev, [id]: checked }));
  }

  function markSelected(status: AttendanceStatus) {
    for (const [id, isSel] of Object.entries(selected)) {
      if (!isSel) continue;
      const i = indexById.get(id);
      if (i === undefined) continue;
      setValue(`rows.${i}.status`, status, { shouldDirty: true });
    }
  }

  // Live counts by status across the whole sheet (not just visible rows).
  const summary = React.useMemo(() => {
    const counts = { present: 0, absent: 0, leave: 0, half_day: 0 };
    for (const r of rows) {
      if (r.status in counts) counts[r.status as keyof typeof counts] += 1;
    }
    return { ...counts, total: rows.length };
  }, [rows]);

  async function onSubmit(values: SheetForm) {
    try {
      const saved = await saveMutation.mutateAsync({
        date,
        records: values.rows.map((r) => ({ employee_id: r.employee_id, status: r.status })),
      });
      // Stay on the page: re-seed from the saved sheet so the form is no
      // longer dirty, and clear selection.
      loadedKey.current = `${saved.attendance_date}:saved`;
      reset({ rows: toRows(saved) });
      setSelected({});
      toast.success("Attendance saved");
    } catch (error) {
      toast.error(
        error instanceof AppError ? error.message : "Couldn't save attendance — try again.",
      );
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      {/* Controls: date + search */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="attendance-date">
              Attendance date
            </label>
            <Input
              id="attendance-date"
              type="date"
              className="sm:w-48"
              value={date}
              onChange={(e) => onDateChange(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="employee-search">
              Search
            </label>
            <Input
              id="employee-search"
              placeholder="Search by name or ID"
              className="sm:w-64"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>
        {query.data?.exists && (
          <span className="text-sm text-muted-foreground">
            Editing attendance already recorded for this date.
          </span>
        )}
      </div>

      {/* Live summary */}
      <Card>
        <CardContent className="flex flex-wrap gap-x-6 gap-y-2 py-3 text-sm">
          <span>
            <span className="font-semibold">{summary.present}</span> Present
          </span>
          <span>
            <span className="font-semibold">{summary.absent}</span> Absent
          </span>
          <span>
            <span className="font-semibold">{summary.leave}</span> Leave
          </span>
          <span>
            <span className="font-semibold">{summary.half_day}</span> Half day
          </span>
          <span className="text-muted-foreground">
            <span className="font-semibold text-foreground">{summary.total}</span> Total
          </span>
        </CardContent>
      </Card>

      {/* Bulk actions */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground">
          {selectedCount} selected
        </span>
        {BULK_ACTIONS.map((s) => (
          <Button
            key={s}
            type="button"
            variant="secondary"
            size="sm"
            disabled={selectedCount === 0}
            onClick={() => markSelected(s)}
          >
            Mark {ATTENDANCE_STATUS_LABEL[s]}
          </Button>
        ))}
      </div>

      {/* Roster table */}
      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-12">
                <SelectAllCheckbox
                  checked={allVisibleSelected}
                  indeterminate={someVisibleSelected}
                  onChange={toggleAllVisible}
                  disabled={visibleIds.length === 0}
                />
              </TableHead>
              <TableHead>Employee</TableHead>
              <TableHead>Employee ID</TableHead>
              <TableHead className="w-48">Status</TableHead>
            </TableRow>
          </TableHeader>

          {query.isLoading && <TableSkeleton cols={4} />}

          {!query.isLoading && !query.isError && visibleIndexes.length > 0 && (
            <TableBody>
              {visibleIndexes.map((i) => {
                const f = fields[i];
                return (
                  <TableRow key={f.id}>
                    <TableCell>
                      <Checkbox
                        checked={!!selected[f.employee_id]}
                        aria-label={`Select ${f.employee_name}`}
                        onChange={(e) => toggleOne(f.employee_id, e.target.checked)}
                      />
                    </TableCell>
                    <TableCell className="font-medium">{f.employee_name}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {f.employee_code}
                    </TableCell>
                    <TableCell>
                      <Controller
                        control={control}
                        name={`rows.${i}.status`}
                        render={({ field }) => (
                          <Select value={field.value} onValueChange={field.onChange}>
                            <SelectTrigger className="w-44">
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
                        )}
                      />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          )}
        </Table>

        {query.isError && (
          <ErrorState
            message="Couldn't load the attendance sheet."
            onRetry={() => void query.refetch()}
          />
        )}
        {!query.isLoading && !query.isError && fields.length === 0 && (
          <EmptyState
            title="No employees"
            description="There are no active employees to record attendance for."
          />
        )}
        {!query.isLoading &&
          !query.isError &&
          fields.length > 0 &&
          visibleIndexes.length === 0 && (
            <EmptyState
              title="No matches"
              description="No employees match your search."
            />
          )}
      </div>

      {/* Single save action */}
      <div className="flex justify-end">
        <Button
          type="submit"
          loading={saveMutation.isPending}
          disabled={saveMutation.isPending || query.isLoading || fields.length === 0}
        >
          Save attendance
        </Button>
      </div>
    </form>
  );
}
