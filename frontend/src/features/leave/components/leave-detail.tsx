"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, ExternalLink } from "lucide-react";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { useAuth } from "@/features/auth/auth-provider";
import { DeliverableStatusBadge } from "@/features/project-deliverables/components/status-badge";
import type { DeliverableStatus } from "@/features/project-deliverables/types";
import { AppError } from "@/lib/api-client";
import { cn } from "@/lib/utils";

import { useDeliverableImpact, useLeaveRequest } from "../hooks";
import { LEAVE_TYPE_LABEL, type DeliverableConflict } from "../types";
import { LeaveStatusBadge } from "./leave-status-badge";

const IMPACT_REASON =
  "Please review the project schedule before approving the leave request.";

// ── helpers ─────────────────────────────────────────────────────────────────

function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const d = m
    ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
    : new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function leaveDays(start: string, end: string): number {
  const diff = Date.parse(end) - Date.parse(start);
  if (Number.isNaN(diff)) return 1;
  return Math.round(diff / 86_400_000) + 1;
}

function InfoRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

// ── conflicting deliverable card ─────────────────────────────────────────────

function ConflictCard({ c }: { c: DeliverableConflict }) {
  const router = useRouter();
  return (
    <div className="rounded-lg border border-border bg-card px-4">
      <div className="divide-y divide-border">
        <InfoRow label="Project" value={c.project_code ?? "—"} />
        <InfoRow label="Activity / Deliverable" value={c.deliverable_name} />
        <InfoRow
          label="Status"
          value={<DeliverableStatusBadge status={c.status as DeliverableStatus} />}
        />
        <InfoRow label="Planned Delivery Date" value={fmtDate(c.target_date)} />
      </div>
      <div className="pb-3 pt-1">
        <Button
          size="sm"
          variant="secondary"
          onClick={() => router.push(`/projects/deliverables/${c.deliverable_id}`)}
        >
          <ExternalLink className="h-3.5 w-3.5" />
          Open Deliverable
        </Button>
      </div>
    </div>
  );
}

// ── page ─────────────────────────────────────────────────────────────────────

export function LeaveDetail({ id }: { id: string }) {
  const { role, employee, employeeId } = useAuth();
  const isManager = role === "project_manager";

  const query = useLeaveRequest(id);
  const { byId } = useEmployeeOptions();

  // Deliverable conflicts are PM-only decision support; the endpoint rejects
  // non-managers, so only query for managers.
  const impactQuery = useDeliverableImpact(isManager ? [id] : []);
  const conflicts =
    impactQuery.data?.items.find((i) => i.leave_request_id === id)?.conflicts ?? [];

  if (query.isLoading) {
    return (
      <>
        <Skeleton className="mb-6 h-10 w-64" />
        <div className="space-y-4">
          <Skeleton className="h-48" />
          <Skeleton className="h-24" />
        </div>
      </>
    );
  }

  if (query.isError || !query.data) {
    const notFound = query.error instanceof AppError && query.error.status === 404;
    return (
      <ErrorState
        title={notFound ? "Leave request not found" : "Couldn't load leave request"}
        message={
          notFound
            ? "This leave request may have been removed."
            : "Please try again."
        }
        onRetry={notFound ? undefined : () => void query.refetch()}
      />
    );
  }

  const leave = query.data;
  const empName =
    byId.get(leave.employee_id) ??
    (leave.employee_id === employeeId ? employee?.full_name : undefined) ??
    leave.employee_id.slice(0, 8);
  const days = leaveDays(leave.start_date, leave.end_date);
  const showImpact = isManager && conflicts.length > 0;

  return (
    <>
      <Link
        href="/attendance?tab=leave"
        className="text-sm text-primary hover:underline"
      >
        ← Leave
      </Link>
      <PageHeader
        className="mt-2"
        title={empName}
        subtitle={`${LEAVE_TYPE_LABEL[leave.leave_type]} leave`}
        actions={<LeaveStatusBadge status={leave.status} />}
      />

      <div className="space-y-4">
        {/* Leave request + deliverable impact, side by side */}
        <div
          className={cn(
            "gap-4",
            showImpact && "grid lg:grid-cols-2 lg:items-start",
          )}
        >
          <Card>
            <CardHeader>
              <CardTitle>Leave Request</CardTitle>
            </CardHeader>
            <CardContent className="divide-y divide-border">
              <InfoRow label="Employee" value={empName} />
              <InfoRow label="Leave Type" value={LEAVE_TYPE_LABEL[leave.leave_type]} />
              <InfoRow label="From" value={fmtDate(leave.start_date)} />
              <InfoRow label="To" value={fmtDate(leave.end_date)} />
              <InfoRow label="Duration" value={`${days} day${days > 1 ? "s" : ""}`} />
              <InfoRow label="Status" value={<LeaveStatusBadge status={leave.status} />} />
              {leave.manager_comment ? (
                <InfoRow label="Manager note" value={leave.manager_comment} />
              ) : null}
            </CardContent>
          </Card>

          {showImpact && (
            <Card className="border-warning/40">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-warning">
                  <AlertTriangle className="h-4 w-4" />
                  Deliverable Impact
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">{IMPACT_REASON}</p>
                <div className="space-y-2.5">
                  {conflicts.map((c) => (
                    <ConflictCard key={c.deliverable_id} c={c} />
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Reason — full width */}
        <Card>
          <CardHeader>
            <CardTitle>Reason</CardTitle>
          </CardHeader>
          <CardContent>
            {leave.reason?.trim() ? (
              <p className="whitespace-pre-wrap text-sm">{leave.reason}</p>
            ) : (
              <p className="text-sm text-muted-foreground">No reason provided.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
