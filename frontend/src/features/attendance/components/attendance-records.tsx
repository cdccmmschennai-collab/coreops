"use client";

import * as React from "react";
import { Pencil } from "lucide-react";

import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Kpi, KpiGrid } from "@/components/ui/kpi";
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
import { nowInIST } from "@/lib/ist";
import { cn } from "@/lib/utils";
import { useUrlState } from "@/lib/use-url-state";

import { AttendanceDayPopover } from "@/features/biometric/components/attendance-day-popover";
import { useDailyReview } from "@/features/biometric/hooks";
import { formatISTTime } from "@/features/biometric/mapping-format";
import {
  CLASSIFICATION_LABEL,
  CLASSIFICATION_VARIANT,
  DEFAULT_REVIEW_FILTER,
  EMPTY,
  filterToClassification,
  formatReviewDate,
  formatWorked,
  isReviewFilter,
  primaryReason,
  REVIEW_FILTERS,
} from "@/features/biometric/review";
import type { DailyReviewRow } from "@/features/biometric/types";

import { RecordDecisionDialog } from "./record-decision-dialog";
import { ATTENDANCE_STATUS_LABEL } from "../schemas";
import type { AttendanceStatus } from "../types";

/**
 * Records tab - the PM's daily attendance review (URL key `history`).
 *
 * A REVIEW SURFACE, not the attendance ledger. Nothing here approves, finalizes
 * or writes anything: every value is read from `GET /biometric/daily-review` and
 * only formatted. `attendance_records` is untouched, and no punch is modified.
 *
 * The screen is built around one question - "what do I need to look at?" - which
 * is why it opens on Needs review rather than on all 29 employees. A day where
 * everything is settled correctly opens empty.
 *
 * What it deliberately does NOT say: that a no-record employee was absent, or
 * that a short day was a half day. Those need the approved leave / permission /
 * official-duty context that Phase 9 integrates.
 */
export function AttendanceRecords() {
  const today = React.useMemo(() => isoInIST(nowInIST()), []);
  // Date and filter live in the URL, so a review can be linked to and survives
  // navigating away and back - the same pattern the rest of the app uses.
  const [rawDate, setDate] = useUrlState("date", today);
  const [rawFilter, setFilter] = useUrlState("review", DEFAULT_REVIEW_FILTER);

  const date = /^\d{4}-\d{2}-\d{2}$/.test(rawDate) ? rawDate : today;
  const filter = isReviewFilter(rawFilter) ? rawFilter : DEFAULT_REVIEW_FILTER;

  const [selected, setSelected] = React.useState<{
    employeeId: string;
    anchor: HTMLElement;
  } | null>(null);
  // The row whose official record the PM is setting, or null.
  const [editing, setEditing] = React.useState<DailyReviewRow | null>(null);

  // A row that is no longer on screen must not keep a popover pointing at it.
  React.useEffect(() => {
    setSelected(null);
  }, [date, filter]);

  const query = useDailyReview({
    date,
    classification: filterToClassification(filter),
  });

  const rows = query.data?.items ?? [];
  const counts = query.data?.counts;
  const openRow = rows.find((r) => r.employee_id === selected?.employeeId);

  const showRows = !query.isLoading && !query.isError && rows.length > 0;
  const showEmpty = !query.isLoading && !query.isError && rows.length === 0;

  return (
    <>
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center">
        <Input
          type="date"
          className="sm:w-44"
          value={date}
          max={today}
          onChange={(e) => e.target.value && setDate(e.target.value)}
          aria-label="Attendance date"
        />
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger className="sm:w-44" aria-label="Review filter">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {REVIEW_FILTERS.map((f) => (
              <SelectItem key={f.value} value={f.value}>
                {f.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-sm text-muted-foreground sm:ml-1">
          {formatReviewDate(date)}
        </p>
      </div>

      {/* Only what biometric evidence can truthfully support. There is no Leave,
          Permission or Half day tile: that data does not exist yet, and a tile
          reading "Leave 0" would be a claim, not a blank. */}
      {counts && (
        <KpiGrid>
          <Kpi label="Present" value={String(counts.present)} />
          <Kpi label="Needs review" value={String(counts.needs_review)} />
          <Kpi label="Incomplete" value={String(counts.incomplete)} />
          <Kpi label="No record" value={String(counts.no_record)} />
        </KpiGrid>
      )}

      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Employee</TableHead>
              <TableHead className="w-24">First IN</TableHead>
              <TableHead className="w-24">Last OUT</TableHead>
              <TableHead className="w-24">Worked</TableHead>
              <TableHead className="w-32">Status</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead className="w-36">Official</TableHead>
            </TableRow>
          </TableHeader>

          {query.isLoading && <TableSkeleton cols={7} />}

          {showRows && (
            <TableBody>
              {rows.map((r) => {
                const reason = primaryReason(r.blocking_reasons);
                return (
                  <TableRow
                    key={r.employee_id}
                    className={cn(
                      "cursor-pointer",
                      r.employee_id === selected?.employeeId && "bg-accent/40",
                    )}
                    onClick={(e) =>
                      setSelected((prev) =>
                        prev?.employeeId === r.employee_id
                          ? null
                          : { employeeId: r.employee_id, anchor: e.currentTarget },
                      )
                    }
                  >
                    <TableCell className="font-medium">
                      {r.employee_name || EMPTY}
                      {r.employee_code && (
                        <span className="ml-1.5 text-xs font-normal text-muted-foreground">
                          {r.employee_code}
                        </span>
                      )}
                    </TableCell>
                    {/* A missing boundary renders as "-", never as a guessed time. */}
                    <TableCell className="tabular">
                      {r.first_in ? formatISTTime(r.first_in) : EMPTY}
                    </TableCell>
                    <TableCell
                      className={cn("tabular", !r.last_out && "text-muted-foreground")}
                    >
                      {r.last_out ? formatISTTime(r.last_out) : EMPTY}
                    </TableCell>
                    <TableCell className="tabular">
                      {formatWorked(r.worked_minutes)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={CLASSIFICATION_VARIANT[r.classification]} dot>
                        {CLASSIFICATION_LABEL[r.classification]}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {reason ?? EMPTY}
                    </TableCell>
                    {/* The human decision, and the way to make or change one.
                        Click is stopped so editing never also opens the
                        read-only popover behind the dialog. */}
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center gap-1.5">
                        {r.attendance_status ? (
                          <Badge variant="outline">
                            {ATTENDANCE_STATUS_LABEL[
                              r.attendance_status as AttendanceStatus
                            ] ?? r.attendance_status}
                          </Badge>
                        ) : (
                          <span className="text-sm text-muted-foreground">{EMPTY}</span>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          aria-label={`Set attendance for ${r.employee_name ?? "employee"}`}
                          onClick={() => setEditing(r)}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          )}
        </Table>

        {query.isError && (
          <ErrorState
            message="Could not load the day's attendance."
            onRetry={() => void query.refetch()}
          />
        )}
        {showEmpty && (
          <EmptyState
            title={
              filter === "needs_review"
                ? "Nothing to review"
                : "No records for this date"
            }
            description={
              filter === "needs_review"
                ? "Every record for this date is either complete biometric evidence or already decided."
                : "No employees match this filter for the selected date."
            }
          />
        )}
      </div>

      <AttendanceDayPopover
        anchor={selected?.anchor ?? null}
        title={openRow?.employee_name || ""}
        subtitle={formatReviewDate(date)}
        summary={openRow as DaySummaryShape | undefined}
        // The official decision wins the status word once one exists, exactly as
        // it does on the employee's own calendar.
        attendanceLabel={
          openRow?.attendance_status
            ? (ATTENDANCE_STATUS_LABEL[
                openRow.attendance_status as AttendanceStatus
              ] ?? openRow.attendance_status)
            : null
        }
        reason={openRow?.attendance_note ?? null}
        onClose={() => setSelected(null)}
      />

      <RecordDecisionDialog
        row={editing}
        date={date}
        onClose={() => {
          setEditing(null);
          // The saved decision changes this row, and the attendance mutation
          // only invalidates attendance queries - the review is a different key.
          void query.refetch();
        }}
      />
    </>
  );
}

/** What the shared popover needs. A review row already satisfies it. */
type DaySummaryShape = Pick<
  DailyReviewRow,
  | "first_in"
  | "last_out"
  | "worked_minutes"
  | "scheduled_minutes"
  | "classification"
  | "review_required"
>;

/** Today's date in Asia/Kolkata as `YYYY-MM-DD`. Never a UTC date: at 02:00 IST
 *  the UTC date is still yesterday, which would open the wrong day. */
function isoInIST(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}
