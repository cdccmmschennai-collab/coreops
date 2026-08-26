"use client";

/**
 * The approval state of ONE lump-sum continuation on a report.
 *
 * ContinuationApprovalCard (next to it in this folder) speaks about an Open Task
 * the employee is about to continue - "continuing this will be sent for
 * approval". This one speaks about work that has already been entered, and its
 * job is to stop a pending continuation from reading as accepted work: a
 * submitted report is not an approved continuation, and the entry has to say so
 * on its own face.
 *
 * All three states render here, and they are the SAME three the backend stores
 * on continuation_requests - there is no second status anywhere:
 *
 *   pending  - entered, submitted, awaiting the Project Head. The report is
 *              submitted regardless; only the activity's completion waits.
 *   approved - ordinary recorded work.
 *   rejected - the rows were withdrawn from the activity list, so what renders
 *              is the surviving request record (report detail passes the
 *              reviewer's note through `note`), which is what keeps a refused
 *              continuation from vanishing out of the employee's history.
 */
import type { ContinuationStatus } from "@/features/work-reports/open-task-state";
import type { WorkReportTask } from "@/features/work-reports/types";

interface Props {
  task: Pick<WorkReportTask, "continuation_approval_status">;
  /** Compact inline form for the editor; the full banner is for the detail page. */
  compact?: boolean;
  /** The reviewer's decision note, shown under a decided state when there is one. */
  note?: string | null;
}

export function ContinuationRowStatus({ task, compact = false, note }: Props) {
  const status = (task.continuation_approval_status ?? null) as ContinuationStatus;
  if (status === null) return null;

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
        {note && <p className="mt-1 text-xs text-muted-foreground">{note}</p>}
      </div>
    );
  }

  if (status === "rejected") {
    return compact ? (
      <span className="text-xs font-medium text-destructive">Continuation rejected</span>
    ) : (
      <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm">
        <p className="font-medium text-destructive">Continuation rejected</p>
        <p className="mt-1 text-xs text-muted-foreground">
          The Project Head rejected continuing this activity beyond its allowed
          duration, so the entry was removed from this report&apos;s activities
          and does not count as recorded work. The rest of the report is
          unaffected.
        </p>
        {note && <p className="mt-1 text-xs text-muted-foreground">{note}</p>}
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
        cannot be marked complete until the continuation is approved. The report
        itself is submitted either way. If it is rejected, this entry is removed
        from the report.
      </p>
    </div>
  );
}
