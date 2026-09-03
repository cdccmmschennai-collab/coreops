"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { toast } from "sonner";

import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAuth } from "@/features/auth/auth-provider";
import { AppError } from "@/lib/api-client";
import { useUrlState } from "@/lib/use-url-state";

import { usePermissionHistory, useRequestPermissionCancellation } from "../hooks";
import {
  currentBusinessMonth,
  formatAvailable,
  formatMonthLabel,
  formatPermissionDuration,
  formatShortDate,
  monthStart,
  permissionCancellationCell,
  permissionDetailPath,
  shiftMonth,
  type PermissionRequest,
} from "../types";
import { PermissionStatusBadge } from "./permission-status-badge";

const COL_COUNT = 5;

/** The employee's own permission history, one calendar month at a time.
 *
 *  Works for project managers too - a PM is an employee and takes permission like
 *  anyone else, and before this there was nowhere for them to see their own.
 *
 *  Reached by clicking the Permission Remaining KPI card. It is a page rather than
 *  a panel inside the KPI so the selected month can live in the URL: going into a
 *  request and pressing Back returns to the same month.
 *
 *  Everything shown comes from ONE call, `/permission-requests/history`: the rows
 *  and the "2h / 4h" figure are two views of the same server-computed month, so
 *  they cannot describe different periods and nothing here recomputes the balance
 *  rule. Rows are filtered by permission_date server-side, never created_at. */
export function PermissionHistory() {
  const router = useRouter();
  const { employeeId } = useAuth();
  // `pm_month` (permission month) - namespaced so it cannot collide with any
  // other month/filter parameter on the attendance screens.
  const [rawMonth, setMonth] = useUrlState("pm_month", currentBusinessMonth());
  const month = monthStart(rawMonth);
  const query = usePermissionHistory(month);
  const requestCancellation = useRequestPermissionCancellation();
  // Only the row being acted on is disabled, so one slow request does not freeze
  // the whole month's table.
  const [pendingId, setPendingId] = React.useState<string | null>(null);

  async function onRequestCancellation(req: PermissionRequest) {
    if (pendingId) return;
    setPendingId(req.id);
    try {
      await requestCancellation.mutateAsync(req.id);
      toast.success(
        "Cancellation requested. It now waits for a reviewer's decision - the " +
          "permission stays approved until then.",
      );
    } catch (err) {
      toast.error(
        err instanceof AppError
          ? err.message
          : "Could not request cancellation of this permission.",
      );
    } finally {
      setPendingId(null);
    }
  }

  const items = query.data?.items ?? [];
  const balance = query.data?.balance;

  return (
    <>
      <Link href="/attendance" className="text-sm text-primary hover:underline">
        ← Attendance
      </Link>
      <PageHeader
        className="mt-2"
        title="Permission History"
        subtitle={formatMonthLabel(month)}
      />

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0 gap-4 border-b border-border px-5 py-3.5">
          <div>
            <CardTitle className="text-base">{formatMonthLabel(month)}</CardTitle>
            <div className="mt-1 text-xs text-muted-foreground">
              Available{" "}
              <span className="tabular font-semibold text-foreground">
                {balance
                  ? formatAvailable(balance.remaining_hours, balance.allowance_hours)
                  : "-"}
              </span>
            </div>
          </div>
          {/* Month navigation. No upper bound: a request may be filed for a
              future date, so next month is a real place to look. */}
          <div className="flex items-center gap-1">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setMonth(shiftMonth(month, -1))}
              aria-label="Previous month"
            >
              <ChevronLeft className="h-4 w-4" />
              Previous
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setMonth(shiftMonth(month, 1))}
              aria-label="Next month"
            >
              Next
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {query.isLoading ? (
            <div className="px-5 py-4">
              <TableSkeleton rows={3} cols={COL_COUNT} />
            </div>
          ) : query.isError ? (
            <div className="px-5 py-8">
              <ErrorState
                title="Couldn't load permission history"
                message="Please try again."
                onRetry={() => void query.refetch()}
              />
            </div>
          ) : items.length === 0 ? (
            <div className="px-5 py-8">
              <EmptyState
                title="No permission requests for this month."
                description={`Nothing was requested in ${formatMonthLabel(month)}.`}
              />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead>Cancellation</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((req) => (
                  <TableRow
                    key={req.id}
                    className="cursor-pointer hover:bg-muted/40"
                    onClick={() => router.push(permissionDetailPath(req.id))}
                  >
                    <TableCell className="tabular font-medium">
                      {formatShortDate(req.permission_date)}
                    </TableCell>
                    <TableCell className="tabular">
                      {formatPermissionDuration(req)}
                    </TableCell>
                    <TableCell>
                      <PermissionStatusBadge status={req.status} />
                    </TableCell>
                    <TableCell className="max-w-[280px] truncate text-muted-foreground">
                      {req.reason?.trim() ? req.reason : "-"}
                    </TableCell>
                    {/* The action must not also open the detail page, so the
                        cell swallows the row's click - the same guard the leave
                        and permission review queues use for their buttons. */}
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <CancellationCell
                        req={req}
                        employeeId={employeeId}
                        busy={pendingId === req.id}
                        disabled={pendingId !== null}
                        onRequest={() => void onRequestCancellation(req)}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  );
}

/** The Cancellation column for one history row.
 *
 *  Three outcomes, decided by the pure `permissionCancellationCell` rule so the
 *  table itself holds no policy: offer the action, say a withdrawal is already
 *  awaiting review, or say nothing. The "already requested" state is what stops
 *  a duplicate being filed from here; the backend refuses one with a 409
 *  whatever this renders. */
function CancellationCell({
  req,
  employeeId,
  busy,
  disabled,
  onRequest,
}: {
  req: PermissionRequest;
  employeeId: string | null | undefined;
  busy: boolean;
  disabled: boolean;
  onRequest: () => void;
}) {
  const cell = permissionCancellationCell(req, employeeId);

  if (cell === "requested") {
    return (
      <span className="text-xs font-medium text-warning">Cancellation requested</span>
    );
  }
  if (cell === "request") {
    return (
      <Button
        size="sm"
        variant="secondary"
        onClick={onRequest}
        loading={busy}
        disabled={disabled}
      >
        Request cancellation
      </Button>
    );
  }
  return <span className="text-muted-foreground">-</span>;
}
