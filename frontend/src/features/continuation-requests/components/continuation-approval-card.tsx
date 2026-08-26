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
        <p className="font-medium">Continuation requested</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {task.continuation_routed_to
            ? `Awaiting Project Head approval from ${task.continuation_routed_to}.`
            : "Awaiting Project Head approval."}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Days you enter for this activity are held under this same review - they
          are not recorded work until it is approved, and the activity cannot be
          marked complete meanwhile. If it is rejected, those entries are removed
          from their reports.
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
