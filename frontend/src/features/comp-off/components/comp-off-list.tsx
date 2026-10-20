"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { AppError } from "@/lib/api-client";

import { useCancelCompOff, useCompOffList } from "../hooks";
import {
  COMP_OFF_PAGE_SIZE,
  COMP_OFF_STATUSES,
  COMP_OFF_STATUS_LABEL,
  canCancel,
  compOffDetailHref,
  compOffErrorMessage,
  formatShortDate,
  type CompOffStatus,
  type CompOffViewer,
} from "../types";
import { CompOffStatusBadge } from "./comp-off-status-badge";

interface Props {
  title: string;
  viewer: CompOffViewer;
  /** The manager's all-requests list: an Employee column and a status filter.
   *  An employee's list has neither - the server already returns only their own
   *  requests, whatever the browser asks for. */
  showEmployee?: boolean;
}

/** A paged list of comp off requests with their decision. Read-only apart from
 *  Cancel on the author's own PENDING request - an approved request is final. */
export function CompOffList({ title, viewer, showEmployee = false }: Props) {
  const router = useRouter();
  const [status, setStatus] = React.useState<CompOffStatus | "">("");
  const [offset, setOffset] = React.useState(0);
  const query = useCompOffList({ status, limit: COMP_OFF_PAGE_SIZE, offset });
  const cancel = useCancelCompOff();

  const items = query.data?.items ?? [];
  const total = query.data?.total ?? 0;
  const colCount = showEmployee ? 7 : 6;

  async function onCancel(id: string) {
    if (cancel.isPending) return;
    try {
      await cancel.mutateAsync(id);
      toast.success("Comp off request cancelled");
    } catch (err) {
      toast.error(
        err instanceof AppError
          ? compOffErrorMessage(err.status, err.message, "cancel the request")
          : compOffErrorMessage(undefined, undefined, "cancel the request"),
      );
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3 border-b border-border px-5 py-3.5">
        <CardTitle className="text-base">{title}</CardTitle>
        {showEmployee && (
          <Select
            value={status || "all"}
            onValueChange={(v) => {
              setStatus(v === "all" ? "" : (v as CompOffStatus));
              setOffset(0);
            }}
          >
            <SelectTrigger className="w-40" aria-label="Filter by status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              {COMP_OFF_STATUSES.map((s) => (
                <SelectItem key={s} value={s}>
                  {COMP_OFF_STATUS_LABEL[s]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </CardHeader>
      <CardContent className="p-0">
        {query.isLoading ? (
          <TableSkeleton rows={3} cols={colCount} />
        ) : query.isError ? (
          <ErrorState
            title="Couldn't load comp off requests"
            message="Check your connection and try again."
            onRetry={() => void query.refetch()}
          />
        ) : items.length === 0 ? (
          <div className="px-5 py-8">
            <EmptyState
              title="No comp off requests"
              description={
                showEmployee
                  ? "No requests match this filter."
                  : "Requests you submit appear here with their decision."
              }
            />
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  {showEmployee && <TableHead>Employee</TableHead>}
                  <TableHead>Day worked</TableHead>
                  <TableHead>Day off</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Requested</TableHead>
                  <TableHead>Decision</TableHead>
                  <TableHead>
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((req) => (
                  <TableRow
                    key={req.id}
                    className="cursor-pointer hover:bg-muted/40"
                    onClick={() => router.push(compOffDetailHref(req.id))}
                  >
                    {showEmployee && (
                      <TableCell className="font-medium">
                        {req.employee_name ?? req.employee_id.slice(0, 8)}
                      </TableCell>
                    )}
                    <TableCell className="tabular">{formatShortDate(req.worked_date)}</TableCell>
                    <TableCell className="tabular">{formatShortDate(req.off_date)}</TableCell>
                    <TableCell>
                      <CompOffStatusBadge status={req.status} />
                    </TableCell>
                    <TableCell className="tabular text-muted-foreground">
                      {formatShortDate(req.created_at)}
                    </TableCell>
                    <TableCell className="max-w-[260px] text-sm text-muted-foreground">
                      {req.reviewed_at ? (
                        <>
                          <div>
                            {formatShortDate(req.reviewed_at)}
                            {req.manager_name ? ` by ${req.manager_name}` : ""}
                          </div>
                          {req.manager_comment && (
                            <div className="truncate" title={req.manager_comment}>
                              {req.status === "rejected" ? "Reason: " : "Note: "}
                              {req.manager_comment}
                            </div>
                          )}
                        </>
                      ) : (
                        "-"
                      )}
                    </TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      {canCancel(req, viewer) && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => void onCancel(req.id)}
                          disabled={cancel.isPending}
                        >
                          Cancel
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {total > COMP_OFF_PAGE_SIZE && (
              <div className="flex items-center justify-between border-t border-border px-5 py-3 text-sm text-muted-foreground">
                <span className="tabular">
                  {offset + 1}-{Math.min(offset + COMP_OFF_PAGE_SIZE, total)} of {total}
                </span>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={offset === 0 || query.isFetching}
                    onClick={() => setOffset(Math.max(0, offset - COMP_OFF_PAGE_SIZE))}
                  >
                    Previous
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={offset + COMP_OFF_PAGE_SIZE >= total || query.isFetching}
                    onClick={() => setOffset(offset + COMP_OFF_PAGE_SIZE)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
