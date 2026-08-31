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
import { AppError } from "@/lib/api-client";

import {
  useApproveLeaveCancellation,
  useLeaveAttendanceSummary,
  useLeaveList,
  useRejectLeaveCancellation,
} from "../hooks";
import {
  LEAVE_TYPE_LABEL,
  attendanceSummaryLabel,
  formatLeavePeriod,
  leaveDetailHref,
  type LeaveRequest,
} from "../types";

const LIMIT = 50;

type Decision = "approve" | "reject";

interface Props {
  /** True only when this panel is reused inside a Project Head's "Team
   *  approvals" tab — excludes the Head's own requests from the queue so they
   *  can't see (and get 403'd trying to act on) their own cancellation request
   *  here. */
  excludeSelf?: boolean;
}

/** PM queue for approved leave employees have asked to withdraw.
 *
 *  Approving cancels the leave outright — there is no second confirmation step
 *  for the employee. Attendance is never touched, which the confirmation says
 *  explicitly so the manager knows to review it afterwards. */
export function LeaveCancellationReviewPanel({ excludeSelf = false }: Props) {
  const router = useRouter();
  const { role } = useAuth();
  const isManager = role === "project_manager";
  const query = useLeaveList({
    status: "cancellation_requested",
    limit: LIMIT,
    offset: 0,
    exclude_self: excludeSelf,
  });
  const approve = useApproveLeaveCancellation();
  const reject = useRejectLeaveCancellation();
  const { byId: empById } = useEmployeeOptions();

  const rows = query.data?.items ?? [];
  const ids = React.useMemo(() => rows.map((r) => r.id), [rows]);
  const COL_COUNT = isManager ? 6 : 5;

  // Attendance summary is PM-only decision support; the endpoint rejects a
  // Project Head, so the call itself — not just the column — is guarded.
  const summaryQuery = useLeaveAttendanceSummary(isManager ? ids : []);
  const summaryById = React.useMemo(() => {
    const map = new Map<string, string>();
    for (const item of summaryQuery.data?.items ?? []) {
      map.set(item.leave_request_id, item.summary);
    }
    return map;
  }, [summaryQuery.data]);

  const [confirming, setConfirming] = React.useState<
    { request: LeaveRequest; decision: Decision } | null
  >(null);
  const busy = approve.isPending || reject.isPending;

  async function onConfirm() {
    if (!confirming || busy) return;
    const { request, decision } = confirming;
    try {
      if (decision === "approve") {
        await approve.mutateAsync(request.id);
        toast.success("Leave cancellation approved. Attendance was not changed.", {
          action: {
            label: "Review attendance",
            onClick: () =>
              router.push(`/attendance?tab=history&employee=${request.employee_id}`),
          },
        });
      } else {
        await reject.mutateAsync(request.id);
        toast.success("Cancellation request rejected. The approved leave remains active.");
      }
      setConfirming(null);
    } catch (err) {
      toast.error(
        err instanceof AppError ? err.message : "Could not update the cancellation request.",
      );
    }
  }

  if (query.isLoading) return <TableSkeleton rows={3} cols={COL_COUNT} />;

  if (rows.length === 0) {
    return (
      <Card>
        <CardContent className="px-5 py-8">
          <EmptyState
            title="No cancellation requests"
            description="Approved leave an employee asks to withdraw will appear here."
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
              {rows.map((req) => (
                <TableRow
                  key={req.id}
                  className="cursor-pointer hover:bg-muted/40"
                  // The Cancellation queue's own address - see the Pending
                  // queue's identical call.
                  onClick={() =>
                    router.push(
                      leaveDetailHref(
                        req.id,
                        `${window.location.pathname}${window.location.search}`,
                      ),
                    )
                  }
                >
                  <TableCell className="font-medium">
                    {req.employee_name ??
                      empById.get(req.employee_id) ??
                      req.employee_id.slice(0, 8)}
                  </TableCell>
                  <TableCell>{LEAVE_TYPE_LABEL[req.leave_type]}</TableCell>
                  <TableCell className="tabular">{req.start_date}</TableCell>
                  <TableCell className="tabular">{req.end_date}</TableCell>
                  {isManager && (
                    <TableCell className="text-muted-foreground">
                      {attendanceSummaryLabel(summaryById.get(req.id))}
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
                        onClick={() => setConfirming({ request: req, decision: "approve" })}
                        disabled={busy}
                      >
                        Approve cancellation
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => setConfirming({ request: req, decision: "reject" })}
                        disabled={busy}
                      >
                        Keep approved leave
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
          request={confirming.request}
          decision={confirming.decision}
          busy={busy}
          onBack={() => setConfirming(null)}
          onConfirm={() => void onConfirm()}
        />
      )}
    </>
  );
}

function ConfirmDialog({
  request,
  decision,
  busy,
  onBack,
  onConfirm,
}: {
  request: LeaveRequest;
  decision: Decision;
  busy: boolean;
  onBack: () => void;
  onConfirm: () => void;
}) {
  const period = formatLeavePeriod(request.start_date, request.end_date);
  const approving = decision === "approve";

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
            {approving ? "Approve leave cancellation?" : "Keep approved leave?"}
          </h2>
          {approving ? (
            <div className="space-y-2 text-sm text-muted-foreground">
              <p>
                This will cancel the approved leave for{" "}
                <span className="font-medium text-foreground">{period}</span>.
              </p>
              <p>
                Attendance will not be changed automatically. Review the employee&apos;s
                attendance after cancellation.
              </p>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              The cancellation request will be rejected and the original approved leave
              for <span className="font-medium text-foreground">{period}</span> will
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
              {approving ? "Approve cancellation" : "Keep approved leave"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
