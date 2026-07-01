"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowDown, ArrowRight, Check, X } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AppError } from "@/lib/api-client";

import {
  useApproveActivityRequest,
  usePendingActivityRequests,
  useRejectActivityRequest,
} from "../hooks";
import { ACTIVITY_REQUEST_STATUS_LABEL, type ActivityRequest } from "../types";

export function ActivityRequestsView() {
  const query = usePendingActivityRequests();
  const approve = useApproveActivityRequest();
  const reject = useRejectActivityRequest();

  // Track which row has an in-flight decision so both buttons on it disable.
  const [acting, setActing] = React.useState<string | null>(null);

  async function decide(
    req: ActivityRequest,
    action: "approve" | "reject",
  ) {
    setActing(req.id);
    try {
      if (action === "approve") {
        await approve.mutateAsync(req.id);
        toast.success("Request approved");
      } else {
        await reject.mutateAsync(req.id);
        toast.success("Request rejected");
      }
    } catch (err) {
      toast.error(
        err instanceof AppError ? err.message : "Could not update the request.",
      );
    } finally {
      setActing(null);
    }
  }

  const requests = query.data ?? [];

  return (
    <>
      <Link href="/" className="text-sm text-primary hover:underline">
        ← Home
      </Link>
      <PageHeader
        className="mt-2"
        title="Activity Requests"
        subtitle="Employees requesting to be added to another activity"
      />

      {query.isLoading ? (
        <Card>
          <CardContent className="space-y-2 p-4">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-5/6" />
            <Skeleton className="h-8 w-3/4" />
          </CardContent>
        </Card>
      ) : query.isError ? (
        <Card>
          <CardContent className="p-0">
            <ErrorState
              title="Could not load activity requests"
              message="Please try again."
              onRetry={() => void query.refetch()}
            />
          </CardContent>
        </Card>
      ) : !requests.length ? (
        <Card>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              No pending activity requests.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {requests.map((r) => (
            <Card key={r.id}>
              <CardContent className="flex flex-col gap-4 pt-6 lg:flex-row lg:items-center">
                <div className="lg:w-44 lg:shrink-0">
                  <p className="text-xs text-muted-foreground">Employee</p>
                  <p className="font-medium">{r.employee_name}</p>
                  <Badge variant="warning" className="mt-1">
                    {ACTIVITY_REQUEST_STATUS_LABEL[r.status]}
                  </Badge>
                </div>

                <div className="flex flex-1 flex-col gap-3 sm:flex-row sm:items-stretch">
                  <ActivityBlock
                    label="Current Approved Activity"
                    projectCode={r.current_project_code}
                    activity={r.current_activity_name}
                    subActivity={r.current_sub_activity_name}
                    muted
                  />
                  <div className="flex items-center justify-center">
                    <ArrowRight className="hidden h-4 w-4 text-muted-foreground sm:block" />
                    <ArrowDown className="h-4 w-4 text-muted-foreground sm:hidden" />
                  </div>
                  <ActivityBlock
                    label="Requested Activity"
                    projectCode={r.project_code}
                    activity={r.activity_name}
                    subActivity={r.sub_activity_name}
                  />
                </div>

                <div className="flex gap-2 lg:shrink-0">
                  <Button
                    size="sm"
                    variant="secondary"
                    loading={acting === r.id && approve.isPending}
                    disabled={acting === r.id}
                    onClick={() => void decide(r, "approve")}
                  >
                    <Check className="h-4 w-4" />
                    Approve
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    loading={acting === r.id && reject.isPending}
                    disabled={acting === r.id}
                    onClick={() => void decide(r, "reject")}
                  >
                    <X className="h-4 w-4 text-destructive" />
                    Reject
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}

/** One activity summary (project code / activity / sub-activity) inside a row. */
function ActivityBlock({
  label,
  projectCode,
  activity,
  subActivity,
  muted,
}: {
  label: string;
  projectCode?: string | null;
  activity?: string | null;
  subActivity?: string | null;
  muted?: boolean;
}) {
  return (
    <div
      className={
        muted
          ? "flex-1 rounded-md border border-border bg-muted/40 p-3"
          : "flex-1 rounded-md border border-primary/30 bg-primary/5 p-3"
      }
    >
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <dl className="space-y-1.5 text-sm">
        <div className="flex gap-2">
          <dt className="w-24 shrink-0 text-xs text-muted-foreground">Project Code</dt>
          <dd className="font-mono font-medium">{projectCode || "—"}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-24 shrink-0 text-xs text-muted-foreground">Activity</dt>
          <dd className="font-medium">{activity || "—"}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-24 shrink-0 text-xs text-muted-foreground">Sub Activity</dt>
          <dd className="font-medium">{subActivity || "—"}</dd>
        </div>
      </dl>
    </div>
  );
}
