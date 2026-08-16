"use client";

import { Suspense } from "react";
import * as React from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Pencil } from "lucide-react";

import { RequireCapability } from "@/components/auth/require-capability";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { nowInIST } from "@/lib/ist";

import { biometricKeys } from "@/features/biometric/keys";
import { useDailyReviewDetail } from "@/features/biometric/hooks";
import { formatISTTime } from "@/features/biometric/mapping-format";
import {
  CLASSIFICATION_LABEL,
  CLASSIFICATION_VARIANT,
  EMPTY,
  formatReviewDate,
  formatWorked,
} from "@/features/biometric/review";
import type { PunchEntry } from "@/features/biometric/types";

import { RecordDecisionDialog } from "@/features/attendance/components/record-decision-dialog";
import { ATTENDANCE_STATUS_LABEL } from "@/features/attendance/schemas";
import type { AttendanceStatus } from "@/features/attendance/types";

const PUNCH_ROLE_LABEL: Record<PunchEntry["role"], string> = {
  first_in: "First IN",
  last_out: "Last OUT",
  punch: "Punch",
};

/** Today's date in Asia/Kolkata as `YYYY-MM-DD`. Mirrors attendance-records.tsx -
 *  never a UTC date, since at 02:00 IST the UTC date is still yesterday. */
function isoInIST(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/**
 * Phase 9B: the PM's daily attendance detail for one employee, one day.
 *
 * Reached only from a Records row click (`attendance-records.tsx`), which
 * always supplies `?date=`; a direct/deep link without one falls back to
 * today rather than rendering blank. Editing reuses `RecordDecisionDialog`
 * unchanged - the same Phase 8 dialog Records itself uses - so there is one
 * decision UI, not two.
 */
function AttendanceRecordDetail() {
  const { employeeId } = useParams<{ employeeId: string }>();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const today = React.useMemo(() => isoInIST(nowInIST()), []);

  const rawDate = searchParams.get("date");
  const date = rawDate && /^\d{4}-\d{2}-\d{2}$/.test(rawDate) ? rawDate : today;

  const [editing, setEditing] = React.useState(false);

  const query = useDailyReviewDetail({ employeeId, date });
  const row = query.data?.row;
  const punches = query.data?.punches ?? [];

  // Restore the exact Records view the PM came from - filter, search and
  // page - not just the date. Without this, "← Records" always lands back on
  // the default "Needs review" filter, and a row the PM just resolved (so it
  // no longer needs review) looks like it disappeared.
  const backParams = new URLSearchParams({ tab: "history", date });
  const backReview = searchParams.get("review");
  const backQ = searchParams.get("q");
  const backOffset = searchParams.get("offset");
  if (backReview) backParams.set("review", backReview);
  if (backQ) backParams.set("q", backQ);
  if (backOffset) backParams.set("offset", backOffset);
  const backHref = `/attendance?${backParams.toString()}`;

  return (
    <RequireCapability capability="attendance.manage">
      <Link
        href={backHref}
        className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Records
      </Link>

      {query.isLoading && (
        <div className="mt-4 space-y-4">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      )}

      {query.isError && (
        <ErrorState
          message="Could not load this employee's attendance for this day."
          onRetry={() => void query.refetch()}
        />
      )}

      {row && (
        <>
          <PageHeader
            className="mt-2"
            title={row.employee_name || "Attendance detail"}
            subtitle={`${row.employee_code ?? ""}${row.employee_code ? " · " : ""}${formatReviewDate(date)}`}
            actions={
              <div className="flex items-center gap-2">
                {row.attendance_status ? (
                  <Badge variant="outline">
                    {ATTENDANCE_STATUS_LABEL[row.attendance_status as AttendanceStatus] ??
                      row.attendance_status}
                  </Badge>
                ) : (
                  <Badge variant="neutral">No decision yet</Badge>
                )}
                <Button size="sm" onClick={() => setEditing(true)}>
                  <Pencil className="h-3.5 w-3.5" />
                  Edit
                </Button>
              </div>
            }
          />

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader className="border-b border-border px-5 py-3.5">
                <CardTitle className="text-base">Attendance summary</CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-3 gap-4 pt-5 text-sm">
                <SummaryField
                  label="First IN"
                  value={row.first_in ? formatISTTime(row.first_in) : EMPTY}
                />
                <SummaryField
                  label="Last OUT"
                  value={row.last_out ? formatISTTime(row.last_out) : EMPTY}
                />
                <SummaryField label="Worked" value={formatWorked(row.worked_minutes)} />
                <div className="col-span-3 border-t border-border pt-3">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Source
                  </p>
                  <p className="mt-0.5 text-sm">{boundarySourceLabel(row)}</p>
                </div>
                <div className="col-span-3">
                  <Badge variant={CLASSIFICATION_VARIANT[row.classification]} dot>
                    {CLASSIFICATION_LABEL[row.classification]}
                  </Badge>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="border-b border-border px-5 py-3.5">
                <CardTitle className="text-base">Official attendance</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 pt-5 text-sm">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Status
                  </p>
                  <p className="mt-0.5">
                    {row.attendance_status
                      ? (ATTENDANCE_STATUS_LABEL[row.attendance_status as AttendanceStatus] ??
                        row.attendance_status)
                      : "No decision yet"}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Reason
                  </p>
                  <p className="mt-0.5 whitespace-pre-line text-muted-foreground">
                    {row.attendance_note?.trim() || "No reason given."}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Decision source
                  </p>
                  <p className="mt-0.5">
                    {row.attendance_status === "leave"
                      ? "Leave"
                      : row.attendance_record_id
                        ? "PM decision"
                        : "Not yet decided"}
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>

          <Card className="mt-4">
            <CardHeader className="border-b border-border px-5 py-3.5">
              <CardTitle className="text-base">Biometric punches</CardTitle>
            </CardHeader>
            <CardContent className="pt-5">
              {punches.length === 0 ? (
                <EmptyState
                  title="No punch"
                  description="The biometric device recorded nothing for this employee on this day."
                />
              ) : (
                <ul className="divide-y divide-border">
                  {punches.map((p, i) => (
                    <li
                      key={`${p.punch_time}-${i}`}
                      className="flex items-center justify-between py-2 text-sm"
                    >
                      <span className="tabular font-medium">{formatISTTime(p.punch_time)}</span>
                      <span className="text-muted-foreground">{PUNCH_ROLE_LABEL[p.role]}</span>
                      <Badge variant="neutral">Device</Badge>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </>
      )}

      <RecordDecisionDialog
        row={editing ? (row ?? null) : null}
        date={date}
        onClose={() => {
          setEditing(false);
          // The saved decision changes this employee's row on both the
          // detail screen and the Records roster (a different query) - and
          // the Calendar's official-status source (attendanceKeys, already
          // invalidated by the mutation itself). Invalidating every
          // biometric query here is the same broad pattern the mapping tab
          // already uses (useInvalidateCodes) for the same reason: the
          // active detail query refetches immediately, and the roster query
          // refetches the next time Records is observed.
          void queryClient.invalidateQueries({ queryKey: biometricKeys.all });
        }}
      />
    </RequireCapability>
  );
}

function SummaryField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="tabular mt-0.5 text-base font-semibold">{value}</p>
    </div>
  );
}

/** "Biometric" when both boundaries are device evidence, "PM entered" when
 *  both were supplied by hand, "Biometric + PM entered" when mixed, or a
 *  plain dash when nothing exists yet for either boundary. */
function boundarySourceLabel(row: {
  first_in_source: "device" | "pm" | null;
  last_out_source: "device" | "pm" | null;
}): string {
  const sources = new Set([row.first_in_source, row.last_out_source].filter(Boolean));
  if (sources.size === 0) return EMPTY;
  if (sources.has("device") && sources.has("pm")) return "Biometric + PM entered";
  if (sources.has("device")) return "Biometric";
  return "PM entered";
}

export default function AttendanceRecordDetailPage() {
  return (
    <Suspense>
      <AttendanceRecordDetail />
    </Suspense>
  );
}
