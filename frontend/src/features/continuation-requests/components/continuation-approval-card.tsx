"use client";

import type { OpenTask } from "@/features/work-reports/types";

import type { ContinuationRequestStatus } from "../types";
import { ContinuationStatusBadge } from "./continuation-status-badge";

interface Props {
  task: OpenTask;
}

export function ContinuationApprovalCard({ task }: Props) {
  const status = (task.continuation_status ?? null) as ContinuationRequestStatus | null;

  if (status === "approved") {
    return (
      <div className="rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm">
        <p className="font-medium text-success">
          Continuation approved — you can continue this activity.
        </p>
      </div>
    );
  }

  if (status === "rejected") {
    return (
      <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm">
        <p className="font-medium text-destructive">Continuation rejected</p>
        <p className="mt-1 text-xs text-muted-foreground">
          You cannot continue this activity. Contact your Project Head for details.
        </p>
      </div>
    );
  }

  if (status === "pending") {
    return (
      <div className="rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-sm">
        <p className="font-medium">Continuation Approval Pending</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {task.continuation_routed_to
            ? `Your request has been sent to: ${task.continuation_routed_to}`
            : "Your request has been sent for review."}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Your existing entries for this activity are saved; further updates will
          remain pending the same review.
        </p>
        <div className="mt-1">
          <ContinuationStatusBadge status="pending" />
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-sm">
      <p className="text-xs text-muted-foreground">
        This activity&apos;s allowed duration ({task.target_days}{" "}
        {task.target_days === 1 ? "day" : "days"}) has passed. Continuing it in
        today&apos;s report will be sent to your Project Head for approval.
      </p>
    </div>
  );
}
