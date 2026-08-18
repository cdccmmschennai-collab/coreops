"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Pencil } from "lucide-react";

import { Pagination } from "@/components/data/pagination";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { nowInIST } from "@/lib/ist";
import { cn } from "@/lib/utils";
import { useUrlState } from "@/lib/use-url-state";

import { biometricKeys } from "@/features/biometric/keys";
import { formatPermission, statusWithPermission } from "@/features/biometric/day-detail";
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

const PAGE_SIZE = 15;

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
 *
 * A row does not open the shared calendar popover: it navigates to a dedicated
 * detail route instead (`/attendance/records/[employeeId]`), a stub until
 * Phase 9B builds it out. Editing stays exactly the Phase 8 flow - the pencil
 * button opens `RecordDecisionDialog` unchanged.
 */
export function AttendanceRecords() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const today = React.useMemo(() => isoInIST(nowInIST()), []);
  // Date, filter, search and page live in the URL, so a review can be linked
  // to and survives navigating away and back - the same pattern the rest of
  // the app uses.
  const [rawDate, setDate] = useUrlState("date", today);
  const [rawFilter, setFilter] = useUrlState("review", DEFAULT_REVIEW_FILTER);
  const [rawQ, setRawQ] = useUrlState("q", "");
  const [rawOffset, setRawOffset] = useUrlState("offset", "0");

  const date = /^\d{4}-\d{2}-\d{2}$/.test(rawDate) ? rawDate : today;
  const filter = isReviewFilter(rawFilter) ? rawFilter : DEFAULT_REVIEW_FILTER;
  const offset = Math.max(0, Number(rawOffset) || 0);

  // Debounced fetch text: the URL (rawQ) updates on every keystroke, but the
  // request only fires 300ms after typing stops - the same pattern the
  // biometric mapping tab uses for its search box.
  const [q, setQ] = React.useState(rawQ);
  React.useEffect(() => {
    const t = setTimeout(() => setQ(rawQ.trim().toLowerCase()), 300);
    return () => clearTimeout(t);
  }, [rawQ]);

  // The row whose official record the PM is setting, or null.
  const [editing, setEditing] = React.useState<DailyReviewRow | null>(null);

  // Any change to what's being viewed starts back at page 1.
  React.useEffect(() => {
    setRawOffset("0");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, filter, q]);

  const query = useDailyReview({
    date,
    classification: filterToClassification(filter),
    q,
    limit: PAGE_SIZE,
    offset,
  });

  const rows = query.data?.items ?? [];
  const counts = query.data?.counts;

  const showRows = !query.isLoading && !query.isError && rows.length > 0;
  const showEmpty = !query.isLoading && !query.isError && rows.length === 0;

  function openDetail(row: DailyReviewRow) {
    // Carry the whole view state through, not just the date - otherwise
    // "← Records" lands back on the default filter and a row that just left
    // "Needs review" (because the PM resolved it) looks like it vanished.
    const sp = new URLSearchParams({ date });
    if (filter !== DEFAULT_REVIEW_FILTER) sp.set("review", filter);
    if (rawQ) sp.set("q", rawQ);
    if (offset > 0) sp.set("offset", String(offset));
    router.push(`/attendance/records/${row.employee_id}?${sp.toString()}`);
  }

  return (
    <>
      <h2 className="mb-3 text-lg font-semibold">Daily Attendance Review</h2>

      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center">
        <Input
          type="date"
          className="sm:w-44"
          value={date}
          max={today}
          onChange={(e) => e.target.value && setDate(e.target.value)}
          aria-label="Attendance date"
        />
        <Input
          type="search"
          placeholder="Search by name or ID"
          className="sm:w-56"
          value={rawQ}
          onChange={(e) => setRawQ(e.target.value)}
          aria-label="Search employees"
        />
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger className="sm:w-44" aria-label="Status filter">
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
      </div>

      {/* Summary counts for the whole day - not just the current page or
          search. Only what biometric evidence can truthfully support: there
          is no Leave, Permission or Half day count here, since that data
          does not exist yet and a count reading "Leave 0" would be a claim,
          not a blank. */}
      {counts && (
        <div className="mb-4 rounded-lg border border-border bg-card px-4 py-3">
          <p className="text-sm font-semibold">{formatReviewDate(date)}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            <span className="font-medium text-foreground tabular">{counts.present}</span>{" "}
            {CLASSIFICATION_LABEL.present}
            <span className="mx-1.5">·</span>
            <span className="font-medium text-foreground tabular">{counts.needs_review}</span>{" "}
            {CLASSIFICATION_LABEL.needs_review}
            <span className="mx-1.5">·</span>
            <span className="font-medium text-foreground tabular">{counts.incomplete}</span>{" "}
            {CLASSIFICATION_LABEL.incomplete}
            <span className="mx-1.5">·</span>
            <span className="font-medium text-foreground tabular">{counts.no_record}</span>{" "}
            {CLASSIFICATION_LABEL.no_record}
          </p>
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Employee</TableHead>
              <TableHead className="w-24">First IN</TableHead>
              <TableHead className="w-24">Last OUT</TableHead>
              <TableHead className="w-24">Worked</TableHead>
              <TableHead className="w-32">Biometric</TableHead>
              <TableHead className="w-32">Status</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead className="w-16 text-right">Action</TableHead>
            </TableRow>
          </TableHeader>

          {query.isLoading && <TableSkeleton cols={8} />}

          {showRows && (
            <TableBody>
              {rows.map((r) => {
                const reason = primaryReason(r.blocking_reasons);
                return (
                  <TableRow
                    key={r.employee_id}
                    className={cn("cursor-pointer")}
                    onClick={() => openDetail(r)}
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
                    {/* RAW BIOMETRIC EVIDENCE: the conservative verdict the punch
                        stream alone supports. */}
                    <TableCell>
                      <Badge variant={CLASSIFICATION_VARIANT[r.classification]} dot>
                        {CLASSIFICATION_LABEL[r.classification]}
                      </Badge>
                    </TableCell>
                    {/* FINAL ATTENDANCE STATUS: the PM's official decision, when
                        one exists. Distinct column from Biometric on purpose - a
                        settled punch record and a human ruling are not the same
                        fact. */}
                    {/* Phase 12: an approved permission is appended here -
                        "Present | 2hr". It never replaces the status and is
                        never shown as Leave; a day with no decision but a
                        permission still reports the hours rather than a dash. */}
                    <TableCell>
                      {r.attendance_status ? (
                        <Badge variant="outline">
                          {statusWithPermission(
                            ATTENDANCE_STATUS_LABEL[
                              r.attendance_status as AttendanceStatus
                            ] ?? r.attendance_status,
                            r.permission_hours,
                          )}
                        </Badge>
                      ) : r.permission_hours != null ? (
                        <span className="text-sm text-muted-foreground">
                          Permission {formatPermission(r.permission_hours)}
                        </span>
                      ) : (
                        <span className="text-sm text-muted-foreground">{EMPTY}</span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {/* Once a PM has decided the day, their stated reason is
                          the useful one to show - the evidence gap that used
                          to block review is no longer what the row is about. */}
                      {r.attendance_note?.trim() || reason || EMPTY}
                    </TableCell>
                    {/* Click is stopped so editing never also triggers the row's
                        navigation to the detail route. */}
                    <TableCell
                      className="text-right"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        aria-label={`Set attendance for ${r.employee_name ?? "employee"}`}
                        onClick={() => setEditing(r)}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
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
        {showRows && query.data && (
          <Pagination
            total={query.data.total}
            limit={query.data.limit}
            offset={query.data.offset}
            onPageChange={(next) => setRawOffset(String(next))}
          />
        )}
      </div>

      <RecordDecisionDialog
        row={editing}
        date={date}
        onClose={() => {
          setEditing(null);
          // The saved decision also changes the employee's Calendar (Phase
          // 9C reads the same merge, under biometricKeys) and the detail
          // route, if either is open elsewhere - not just this table's own
          // query. Same broad-invalidation pattern the mapping tab and the
          // detail page already use, rather than a narrower refetch here and
          // a different one there.
          void queryClient.invalidateQueries({ queryKey: biometricKeys.all });
        }}
      />
    </>
  );
}

/** Today's date in Asia/Kolkata as `YYYY-MM-DD`. Never a UTC date: at 02:00 IST
 *  the UTC date is still yesterday, which would open the wrong day. */
function isoInIST(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}
