"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { EmptyState } from "@/components/feedback/empty-state";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { useAuth } from "@/features/auth/auth-provider";
import {
  useApprovePermissionCancellation,
  usePermissionList,
  useRejectPermissionCancellation,
} from "@/features/permissions/hooks";
import {
  formatPermissionDuration,
  permissionDetailHref,
  type PermissionRequest,
} from "@/features/permissions/types";
import { AppError } from "@/lib/api-client";

import {
  useApproveLeaveCancellation,
  useLeaveAttendanceSummary,
  useLeaveList,
  useRejectLeaveCancellation,
} from "../hooks";
import {
  attendanceSummaryLabel,
  formatLeavePeriod,
  leaveDetailHref,
  leaveTypeLabel,
  type LeaveRequest,
} from "../types";

const LIMIT = 50;

type Decision = "approve" | "reject";

/** One row of the shared queue, whichever kind of absence it came from.
 *
 *  Flattened deliberately: the table renders five columns that mean the same
 *  thing for both kinds, and every difference that is left - the label, where
 *  the row navigates, which mutation the buttons call - is carried here rather
 *  than branched on in the markup. */
type QueueRow = {
  id: string;
  kind: "leave" | "permission";
  employeeId: string;
  employeeName: string | null;
  /** The one cell that tells a reviewer WHAT they are looking at. */
  typeLabel: string;
  from: string;
  to: string;
  createdAt: string;
  /** What the confirmation dialog names, e.g. "17 Aug 2026" or a leave period. */
  period: string;
};

interface Props {
  /** True only when this panel is reused inside a Project Head's "Team
   *  approvals" tab — excludes the Head's own requests from BOTH queries so they
   *  can't see (and get 403'd trying to act on) their own cancellation request
   *  here. */
  excludeSelf?: boolean;
}

/** The shared cancellation queue: approved LEAVE and approved PERMISSION an
 *  employee has asked to withdraw, in one work list.
 *
 *  Permission joined it in Phase 4E rather than getting a tab of its own, because
 *  it is the same question asked about a smaller absence - the reviewer decides
 *  whether a granted absence stands. The Type column is what tells them apart;
 *  everything else about the leave half is exactly as it was.
 *
 *  WHICH ROWS EACH READER SEES IS NOT DECIDED HERE. Both `/leave-requests` and
 *  `/permission-requests` are already scoped server-side to the projects the
 *  caller heads (a PM sees everything), so the same two calls serve both readers.
 *
 *  Approving cancels the absence outright — there is no second confirmation step
 *  for the employee. Attendance is never touched, which the leave confirmation
 *  says explicitly so the manager knows to review it afterwards. */
export function LeaveCancellationReviewPanel({ excludeSelf = false }: Props) {
  const router = useRouter();
  const { role } = useAuth();
  const isManager = role === "project_manager";
  const leaveQuery = useLeaveList({
    status: "cancellation_requested",
    limit: LIMIT,
    offset: 0,
    exclude_self: excludeSelf,
  });
  const permissionQuery = usePermissionList({
    status: "cancellation_requested",
    limit: LIMIT,
    offset: 0,
    exclude_self: excludeSelf,
  });
  const approveLeave = useApproveLeaveCancellation();
  const rejectLeave = useRejectLeaveCancellation();
  const approvePermission = useApprovePermissionCancellation();
  const rejectPermission = useRejectPermissionCancellation();
  const { byId: empById } = useEmployeeOptions();

  const leaveRows = React.useMemo(
    () => leaveQuery.data?.items ?? [],
    [leaveQuery.data],
  );
  const permissionRows = React.useMemo(
    () => permissionQuery.data?.items ?? [],
    [permissionQuery.data],
  );
  const COL_COUNT = isManager ? 6 : 5;

  // Attendance summary is PM-only decision support and is a LEAVE endpoint, so
  // the call itself — not just the column — is guarded, and it is asked only
  // about the leave half of the queue.
  const leaveIds = React.useMemo(() => leaveRows.map((r) => r.id), [leaveRows]);
  const summaryQuery = useLeaveAttendanceSummary(isManager ? leaveIds : []);
  const summaryById = React.useMemo(() => {
    const map = new Map<string, string>();
    for (const item of summaryQuery.data?.items ?? []) {
      map.set(item.leave_request_id, item.summary);
    }
    return map;
  }, [summaryQuery.data]);

  const rows = React.useMemo<QueueRow[]>(() => {
    const merged: QueueRow[] = [
      ...leaveRows.map(toLeaveRow),
      ...permissionRows.map(toPermissionRow),
    ];
    // Newest ask first, across both kinds — the order a manager works a queue
    // in, and the same order each list already came back in on its own.
    return merged.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  }, [leaveRows, permissionRows]);

  const [confirming, setConfirming] = React.useState<
    { row: QueueRow; decision: Decision } | null
  >(null);
  const busy =
    approveLeave.isPending ||
    rejectLeave.isPending ||
    approvePermission.isPending ||
    rejectPermission.isPending;

  async function onConfirm() {
    if (!confirming || busy) return;
    const { row, decision } = confirming;
    try {
      if (row.kind === "leave") {
        if (decision === "approve") {
          await approveLeave.mutateAsync(row.id);
          toast.success("Leave cancellation approved. Attendance was not changed.", {
            action: {
              label: "Review attendance",
              onClick: () =>
                router.push(`/attendance?tab=history&employee=${row.employeeId}`),
            },
          });
        } else {
          await rejectLeave.mutateAsync(row.id);
          toast.success("Cancellation request rejected. The approved leave remains active.");
        }
      } else if (decision === "approve") {
        await approvePermission.mutateAsync(row.id);
        toast.success(
          "Permission cancellation approved. The hours are back in the employee's allowance.",
        );
      } else {
        await rejectPermission.mutateAsync(row.id);
        toast.success(
          "Cancellation request rejected. The approved permission remains active.",
        );
      }
      setConfirming(null);
    } catch (err) {
      toast.error(
        err instanceof AppError ? err.message : "Could not update the cancellation request.",
      );
    }
  }

  if (leaveQuery.isLoading || permissionQuery.isLoading) {
    return <TableSkeleton rows={3} cols={COL_COUNT} />;
  }

  if (rows.length === 0) {
    return (
      <Card>
        <CardContent className="px-5 py-8">
          <EmptyState
            title="No cancellation requests"
            description="Approved leave and permission an employee asks to withdraw will appear here."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Employee</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>From</TableHead>
                <TableHead>To</TableHead>
                {isManager && <TableHead>Attendance</TableHead>}
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow
                  key={`${row.kind}-${row.id}`}
                  className="cursor-pointer hover:bg-muted/40"
                  // Each kind's own detail page, both carrying THIS queue's own
                  // live address so either detail page comes back here. The
                  // permission half used to pass a bare path, which left its
                  // detail page with nothing to return to and dropped the
                  // reviewer on their own Permission History instead.
                  onClick={() =>
                    router.push(
                      (row.kind === "leave" ? leaveDetailHref : permissionDetailHref)(
                        row.id,
                        `${window.location.pathname}${window.location.search}`,
                      ),
                    )
                  }
                >
                  <TableCell className="font-medium">
                    {row.employeeName ??
                      empById.get(row.employeeId) ??
                      row.employeeId.slice(0, 8)}
                  </TableCell>
                  <TableCell>{row.typeLabel}</TableCell>
                  <TableCell className="tabular">{row.from}</TableCell>
                  <TableCell className="tabular">{row.to}</TableCell>
                  {isManager && (
                    <TableCell className="text-muted-foreground">
                      {/* Leave-only decision support: there is no permission
                          equivalent, and a permission day stays `present` in
                          attendance either way. */}
                      {row.kind === "leave"
                        ? attendanceSummaryLabel(summaryById.get(row.id))
                        : "-"}
                    </TableCell>
                  )}
                  <TableCell>
                    <div
                      className="flex items-center gap-1"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={() => setConfirming({ row, decision: "approve" })}
                        disabled={busy}
                      >
                        Approve cancellation
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => setConfirming({ row, decision: "reject" })}
                        disabled={busy}
                      >
                        {row.kind === "leave"
                          ? "Keep approved leave"
                          : "Keep approved permission"}
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {confirming && (
        <ConfirmDialog
          row={confirming.row}
          decision={confirming.decision}
          busy={busy}
          onBack={() => setConfirming(null)}
          onConfirm={() => void onConfirm()}
        />
      )}
    </>
  );
}

// ── row builders ────────────────────────────────────────────────────────────

function toLeaveRow(req: LeaveRequest): QueueRow {
  return {
    id: req.id,
    kind: "leave",
    employeeId: req.employee_id,
    employeeName: req.employee_name,
    // "Leave - Normal" / "Leave - Special", prefixed with the kind so the two
    // halves of the queue are distinguishable at a glance - and "Leave - Half
    // Day (First)" for a half-day request, through the same precedence every
    // other Type cell applies.
    typeLabel: `Leave - ${leaveTypeLabel(req)}`,
    from: req.start_date,
    to: req.end_date,
    createdAt: req.created_at,
    period: formatLeavePeriod(req.start_date, req.end_date),
  };
}

function toPermissionRow(req: PermissionRequest): QueueRow {
  return {
    id: req.id,
    kind: "permission",
    employeeId: req.employee_id,
    employeeName: req.employee_name,
    // The selected option, e.g. "Permission - 1st Half - 1 Hour", so the Type
    // cell carries the same "what exactly" a leave row's classification does.
    typeLabel: `Permission - ${formatPermissionDuration(req)}`,
    // A permission is always a single day, so From and To are that day. Stating
    // it twice is truthful and keeps one table shape for both kinds.
    from: req.permission_date,
    to: req.permission_date,
    createdAt: req.created_at,
    period: req.permission_date,
  };
}

function ConfirmDialog({
  row,
  decision,
  busy,
  onBack,
  onConfirm,
}: {
  row: QueueRow;
  decision: Decision;
  busy: boolean;
  onBack: () => void;
  onConfirm: () => void;
}) {
  const approving = decision === "approve";
  const isLeave = row.kind === "leave";
  const noun = isLeave ? "leave" : "permission";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-foreground/40"
        onClick={() => !busy && onBack()}
        aria-hidden
      />
      <Card className="relative z-10 w-full max-w-md shadow-xl">
        <CardContent className="space-y-4 pt-5">
          <h2 className="text-base font-semibold">
            {approving
              ? `Approve ${noun} cancellation?`
              : `Keep approved ${noun}?`}
          </h2>
          {approving ? (
            <div className="space-y-2 text-sm text-muted-foreground">
              <p>
                This will cancel the approved {noun} for{" "}
                <span className="font-medium text-foreground">{row.period}</span>.
              </p>
              {isLeave ? (
                <p>
                  Attendance will not be changed automatically. Review the employee&apos;s
                  attendance after cancellation.
                </p>
              ) : (
                <p>
                  The hours return to the employee&apos;s allowance for that month.
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              The cancellation request will be rejected and the original approved{" "}
              {noun} for{" "}
              <span className="font-medium text-foreground">{row.period}</span> will
              remain active.
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onBack} disabled={busy}>
              Back
            </Button>
            <Button
              variant={approving ? "danger" : "secondary"}
              onClick={onConfirm}
              loading={busy}
              disabled={busy}
            >
              {approving
                ? "Approve cancellation"
                : `Keep approved ${noun}`}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
