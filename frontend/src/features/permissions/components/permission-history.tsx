"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight } from "lucide-react";

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
import { useUrlState } from "@/lib/use-url-state";

import { usePermissionHistory } from "../hooks";
import {
  currentBusinessMonth,
  formatAvailable,
  formatMonthLabel,
  formatPermissionDuration,
  formatShortDate,
  monthStart,
  permissionDetailPath,
  shiftMonth,
} from "../types";
import { PermissionStatusBadge } from "./permission-status-badge";

const COL_COUNT = 4;

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
  // `pm_month` (permission month) - namespaced so it cannot collide with any
  // other month/filter parameter on the attendance screens.
  const [rawMonth, setMonth] = useUrlState("pm_month", currentBusinessMonth());
  const month = monthStart(rawMonth);
  const query = usePermissionHistory(month);

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
