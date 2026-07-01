"use client";

import * as React from "react";
import { Check, X } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
      <PageHeader
        title="Activity Requests"
        subtitle="Employees requesting to be added to another activity"
      />

      <Card>
        <CardContent className="p-0">
          {query.isLoading ? (
            <div className="space-y-2 p-4">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-5/6" />
              <Skeleton className="h-8 w-3/4" />
            </div>
          ) : query.isError ? (
            <ErrorState
              title="Could not load activity requests"
              message="Please try again."
              onRetry={() => void query.refetch()}
            />
          ) : !requests.length ? (
            <p className="p-6 text-sm text-muted-foreground">
              No pending activity requests.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Employee</TableHead>
                  <TableHead>Project</TableHead>
                  <TableHead>Activity</TableHead>
                  <TableHead>Sub Activity</TableHead>
                  <TableHead>Task</TableHead>
                  <TableHead className="text-right">Tags</TableHead>
                  <TableHead className="text-right">Docs</TableHead>
                  <TableHead className="text-right">BOM</TableHead>
                  <TableHead className="text-right">Spares</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-32 text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {requests.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="font-medium">{r.employee_name}</TableCell>
                    <TableCell className="text-sm">
                      <span className="font-mono">{r.project_code}</span>
                      {r.project_name && (
                        <span className="ml-1 text-muted-foreground">
                          {r.project_name}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">
                      {r.activity_name ?? (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">{r.sub_activity_name}</TableCell>
                    <TableCell className="text-sm">
                      {r.task_title ?? (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular">{r.tags_count}</TableCell>
                    <TableCell className="text-right tabular">{r.docs_count}</TableCell>
                    <TableCell className="text-right tabular">{r.bom_count}</TableCell>
                    <TableCell className="text-right tabular">{r.spares_count}</TableCell>
                    <TableCell>
                      <Badge variant="warning">
                        {ACTIVITY_REQUEST_STATUS_LABEL[r.status]}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
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
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  );
}
