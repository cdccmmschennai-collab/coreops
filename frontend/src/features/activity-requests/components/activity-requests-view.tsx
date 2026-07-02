"use client";

import * as React from "react";
import Link from "next/link";
import { Check, X } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
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
        <div className="space-y-4">
          {requests.map((r) => (
            <Card key={r.id}>
              <CardHeader className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-center sm:justify-between sm:space-y-0">
                <div className="flex items-center gap-3">
                  <span className="text-base font-semibold text-foreground">
                    {r.employee_name}
                  </span>
                  <Badge variant="warning" dot>
                    {ACTIVITY_REQUEST_STATUS_LABEL[r.status]}
                  </Badge>
                </div>

                <div className="flex gap-2">
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
              </CardHeader>

              <CardContent className="grid grid-cols-1 gap-4 pt-6 md:grid-cols-2">
                <ActivityBlock
                  label="Current Activity"
                  projectCode={r.current_project_code}
                  activity={r.current_activity_name}
                  subActivity={r.current_sub_activity_name}
                  muted
                />
                <ActivityBlock
                  label="Requested Activity"
                  projectCode={r.project_code}
                  activity={r.activity_name}
                  subActivity={r.sub_activity_name}
                />
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
          ? "rounded-lg border border-border bg-muted/30 p-4"
          : "rounded-lg border border-primary/20 bg-primary/5 p-4"
      }
    >
      <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <dl className="space-y-2 text-sm">
        <div className="flex gap-2">
          <dt className="w-24 shrink-0 text-xs text-muted-foreground">Project Code</dt>
          <dd className="font-mono font-medium">{projectCode || "-"}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-24 shrink-0 text-xs text-muted-foreground">Activity</dt>
          <dd className="font-medium">{activity || "-"}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-24 shrink-0 text-xs text-muted-foreground">Sub Activity</dt>
          <dd className="font-medium">{subActivity || "-"}</dd>
        </div>
      </dl>
    </div>
  );
}
