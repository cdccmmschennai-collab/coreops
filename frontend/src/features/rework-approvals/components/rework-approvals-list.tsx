"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { RotateCcw } from "lucide-react";

import { ErrorState } from "@/components/feedback/error-state";
import { Pagination } from "@/components/data/pagination";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Combobox } from "@/components/ui/combobox";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { useUrlState } from "@/lib/use-url-state";

import { useReworkFilterOptions, useReworkRequests } from "../hooks";
import {
  PAGE_SIZE,
  STATUS_LABEL,
  STATUS_TONE,
  dayPartLabel,
  employeeLabel,
  hasActiveFilters,
} from "../labels";
import type { ReworkFilters, ReworkStatus } from "../types";

const ALL = "__all__";

function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/**
 * Activity Requests -> Rework Approvals. Every filter lives in the URL
 * (useUrlState), so opening a request and pressing Back returns to the same
 * filtered page. The page must sit inside a Suspense boundary.
 */
export function ReworkApprovalsList() {
  const router = useRouter();
  const [status, setStatus] = useUrlState("rw_status", "");
  const [projectId, setProjectId] = useUrlState("rw_project", "");
  const [employeeId, setEmployeeId] = useUrlState("rw_employee", "");
  const [reportDate, setReportDate] = useUrlState("rw_date", "");
  const [subActivityId, setSubActivityId] = useUrlState("rw_activity", "");
  const [offsetRaw, setOffsetRaw] = useUrlState("rw_offset", "0");
  const offset = Math.max(0, Number(offsetRaw) || 0);

  const filters: ReworkFilters = {
    status,
    project_id: projectId,
    employee_id: employeeId,
    report_date: reportDate,
    sub_activity_id: subActivityId,
    offset,
  };
  const query = useReworkRequests(filters);
  const options = useReworkFilterOptions();

  // Any filter change starts again at page 1.
  function withReset(setter: (v: string) => void) {
    return (v: string) => {
      setter(v);
      setOffsetRaw("0");
    };
  }

  function clearAll() {
    setStatus("");
    setProjectId("");
    setEmployeeId("");
    setReportDate("");
    setSubActivityId("");
    setOffsetRaw("0");
  }

  const counts = query.data?.counts ?? { pending: 0, approved: 0, rejected: 0 };
  const items = query.data?.items ?? [];

  return (
    <div className="space-y-4">
      {/* Summary cards double as a status filter. */}
      <div className="grid grid-cols-3 gap-3">
        {(["pending", "approved", "rejected"] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => withReset(setStatus)(status === s ? "" : s)}
            aria-pressed={status === s}
            className={cn(
              "rounded-lg border border-border bg-card p-3 text-left transition-colors hover:bg-muted/40",
              status === s && "ring-2 ring-primary/40",
            )}
          >
            <p className="text-xs text-muted-foreground">{STATUS_LABEL[s]}</p>
            <p
              className={cn(
                "mt-1 text-2xl font-semibold tabular-nums",
                s === "pending" && "text-warning",
                s === "approved" && "text-success",
                s === "rejected" && "text-destructive",
              )}
            >
              {counts[s]}
            </p>
          </button>
        ))}
      </div>

      <Card>
        <CardContent className="grid grid-cols-1 gap-2 p-3 sm:grid-cols-2 lg:grid-cols-[repeat(5,minmax(0,1fr))_auto]">
          <Combobox
            value={projectId}
            onValueChange={withReset(setProjectId)}
            options={options.data?.projects ?? []}
            placeholder="All projects"
            searchPlaceholder="Search projects..."
            emptyMessage="No projects."
            allowClear
          />
          <Combobox
            value={employeeId}
            onValueChange={withReset(setEmployeeId)}
            options={options.data?.employees ?? []}
            placeholder="All employees"
            searchPlaceholder="Search employees..."
            emptyMessage="No employees."
            allowClear
          />
          <Input
            type="date"
            value={reportDate}
            onChange={(e) => withReset(setReportDate)(e.target.value)}
            aria-label="Reporting date"
          />
          <Combobox
            value={subActivityId}
            onValueChange={withReset(setSubActivityId)}
            options={options.data?.activities ?? []}
            placeholder="All activities"
            searchPlaceholder="Search activities..."
            emptyMessage="No activities."
            allowClear
          />
          <Select
            value={status || ALL}
            onValueChange={(v) => withReset(setStatus)(v === ALL ? "" : v)}
          >
            <SelectTrigger aria-label="Approval status">
              <SelectValue placeholder="All statuses" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All statuses</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="approved">Approved</SelectItem>
              <SelectItem value="rejected">Rejected</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="ghost"
            size="sm"
            className="h-9 justify-self-start"
            onClick={clearAll}
            disabled={!hasActiveFilters(filters)}
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Clear
          </Button>
        </CardContent>
      </Card>

      <Card className="overflow-hidden p-0">
        {query.isLoading ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-5/6" />
            <Skeleton className="h-8 w-3/4" />
          </div>
        ) : query.isError ? (
          <ErrorState
            title="Could not load rework requests"
            message="Please try again."
            onRetry={() => void query.refetch()}
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Employee</TableHead>
                    <TableHead>Project</TableHead>
                    <TableHead>Activity</TableHead>
                    <TableHead className="whitespace-nowrap">Date</TableHead>
                    <TableHead className="w-28">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-muted-foreground">
                        No rework requests match these filters.
                      </TableCell>
                    </TableRow>
                  )}
                  {items.map((r) => (
                    <TableRow
                      key={r.id}
                      className={cn(
                        "cursor-pointer",
                        r.status === "pending" && "bg-warning/5",
                      )}
                      // ?from=list tells the detail page its Back can return
                      // here with the filters intact (see ReworkBackButton).
                      onClick={() => router.push(`/activity-requests/rework/${r.id}?from=list`)}
                    >
                      <TableCell className="font-medium">
                        {employeeLabel(r.employee_code, r.employee_name)}
                      </TableCell>
                      <TableCell className="text-sm">
                        {r.project_code || r.project_name || "-"}
                      </TableCell>
                      <TableCell className="text-sm">
                        <span className="block">{r.sub_activity_name}</span>
                        <span className="text-xs text-muted-foreground">
                          {r.activity_name ?? "-"} | {dayPartLabel(r.day_part)}
                          {r.cycle_no > 1 ? ` | Attempt ${r.cycle_no}` : ""}
                        </span>
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-sm">
                        {formatDate(r.report_date)}
                      </TableCell>
                      <TableCell>
                        <Badge variant={STATUS_TONE[r.status as ReworkStatus]} dot>
                          {STATUS_LABEL[r.status as ReworkStatus]}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <Pagination
              total={query.data?.total ?? 0}
              limit={PAGE_SIZE}
              offset={offset}
              onPageChange={(next) => setOffsetRaw(String(next))}
            />
          </>
        )}
      </Card>
    </div>
  );
}
