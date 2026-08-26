"use client";

/**
 * The approval state of ONE saved task row on a report.
 *
 * ContinuationApprovalCard (next to it in this folder) speaks about an Open Task
 * the employee is about to continue - "continuing this will be sent for
 * approval". This one speaks about work that has already been entered, and its
 * job is to stop a pending continuation from reading as accepted work: a
 * submitted report is not an approved continuation, and the row has to say so on
 * its own face.
 *
 * Only two states ever reach here. A row needing no approval carries no status
 * and renders nothing; a REJECTED continuation is withdrawn from its report by
 * the backend, so there is no rejected row left to label.
 */
import type { WorkReportTask } from "@/features/work-reports/types";

interface Props {
  task: Pick<WorkReportTask, "continuation_approval_status">;
  /** Compact inline form for the editor; the full banner is for the detail page. */
  compact?: boolean;
}

export function ContinuationRowStatus({ task, compact = false }: Props) {
  const status = task.continuation_approval_status ?? null;
  if (status !== "pending" && status !== "approved") return null;

  if (status === "approved") {
    return compact ? (
      <span className="text-xs font-medium text-success">Continuation approved</span>
    ) : (
      <div className="rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm">
        <p className="font-medium text-success">Continuation approved</p>
        <p className="mt-1 text-xs text-muted-foreground">
          This entry is beyond the activity&apos;s allowed duration and the
          Project Head approved it. It counts as recorded work.
        </p>
      </div>
    );
  }

  return compact ? (
    <span className="text-xs font-medium text-warning">
      Continuation requested - awaiting Project Head approval
    </span>
  ) : (
    <div className="rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-sm">
      <p className="font-medium">Continuation requested</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Awaiting Project Head approval. This entry is beyond the activity&apos;s
        allowed duration, so it is not recorded work yet - and the activity
        cannot be marked complete until the continuation is approved. If it is
        rejected, this entry is removed from the report.
      </p>
    </div>
  );
}
