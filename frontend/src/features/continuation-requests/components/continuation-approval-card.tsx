"use client";

import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { OpenTask } from "@/features/work-reports/types";
import { AppError } from "@/lib/api-client";

import { useCreateContinuationRequest } from "../hooks";
import type { ContinuationRequestStatus } from "../types";
import { ContinuationStatusBadge } from "./continuation-status-badge";

interface Props {
  task: OpenTask;
  reportDate: string;
  onContinue: () => void;
}

export function ContinuationApprovalCard({ task, reportDate, onContinue }: Props) {
  const createRequest = useCreateContinuationRequest();
  const status = (task.continuation_status ?? null) as ContinuationRequestStatus | null;

  async function requestApproval() {
    try {
      await createRequest.mutateAsync({
        work_item_id: task.work_item_id,
        continuation_date: reportDate,
      });
      toast.success("Continuation approval requested");
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not submit the request.");
    }
  }

  if (status === "approved") {
    return (
      <div className="space-y-2 rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm">
        <p className="font-medium text-success">Continuation approved</p>
        <Button type="button" size="sm" variant="secondary" onClick={onContinue}>
          Continue in today&apos;s report
        </Button>
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
          You cannot continue this activity until it is approved.
        </p>
        <div className="mt-1">
          <ContinuationStatusBadge status="pending" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded-md border border-border bg-muted/30 px-3 py-2 text-sm">
      <p className="font-medium">Continuation approval required</p>
      <p className="text-xs text-muted-foreground">
        This activity&apos;s allowed duration ({task.target_days}{" "}
        {task.target_days === 1 ? "day" : "days"}) has passed. You need Project Head approval
        before continuing.
      </p>
      <Button
        type="button"
        size="sm"
        variant="secondary"
        onClick={() => void requestApproval()}
        loading={createRequest.isPending}
      >
        Request Continuation Approval
      </Button>
    </div>
  );
}
