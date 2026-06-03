"use client";

import * as React from "react";
import { useSearchParams, usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/features/auth/auth-provider";
import { isManagerial } from "@/lib/rbac";

import { useLeaveList } from "../hooks";
import { LEAVE_TYPE_LABEL } from "../types";
import type { LeaveStatus } from "../types";
import { LeaveHistory } from "./leave-history";
import { LeaveReviewPanel } from "./leave-review-panel";
import { LeaveStatusBadge } from "./leave-status-badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import { EmptyState } from "@/components/feedback/empty-state";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { Pagination } from "@/components/data/pagination";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const LIMIT = 20;
const ALL = "__all__";

const STATUS_OPTIONS: { value: LeaveStatus | ""; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "cancelled", label: "Cancelled" },
];

/** Admin-level full leave list with filters. */
function AdminLeaveList() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { byId: empById } = useEmployeeOptions();

  const status = (searchParams.get("ls") ?? "") as LeaveStatus | "";
  const employeeId = searchParams.get("le") ?? "";
  const offset = Math.max(0, Number(searchParams.get("lo") ?? "0") || 0);

  function patch(key: string, val: string) {
    const next = new URLSearchParams(searchParams.toString());
    if (val) next.set(key, val); else next.delete(key);
    next.delete("lo");
    router.replace(`${pathname}?${next.toString()}`);
  }

  const query = useLeaveList({ status, employee_id: employeeId || undefined, limit: LIMIT, offset });
  const items = query.data?.items ?? [];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <Select value={status || ALL} onValueChange={(v) => patch("ls", v === ALL ? "" : v)}>
          <SelectTrigger className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((o) => (
              <SelectItem key={o.value || ALL} value={o.value || ALL}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {query.isLoading ? (
        <TableSkeleton rows={5} cols={6} />
      ) : items.length === 0 ? (
        <EmptyState title="No leave requests" description="No requests match the current filters." />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Employee</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>From</TableHead>
                <TableHead>To</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Manager note</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((req) => (
                <TableRow key={req.id}>
                  <TableCell className="font-medium">
                    {empById.get(req.employee_id) ?? req.employee_id.slice(0, 8)}
                  </TableCell>
                  <TableCell>{LEAVE_TYPE_LABEL[req.leave_type]}</TableCell>
                  <TableCell className="tabular">{req.start_date}</TableCell>
                  <TableCell className="tabular">{req.end_date}</TableCell>
                  <TableCell><LeaveStatusBadge status={req.status} /></TableCell>
                  <TableCell className="max-w-[160px] truncate text-muted-foreground">
                    {req.reason ?? "—"}
                  </TableCell>
                  <TableCell className="max-w-[160px] truncate text-muted-foreground">
                    {req.manager_comment ?? "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {(query.data?.total ?? 0) > LIMIT && (
            <Pagination
              total={query.data?.total ?? 0}
              limit={LIMIT}
              offset={offset}
              onPageChange={(o) => {
                const next = new URLSearchParams(searchParams.toString());
                if (o > 0) next.set("lo", String(o)); else next.delete("lo");
                router.replace(`${pathname}?${next.toString()}`);
              }}
            />
          )}
        </>
      )}
    </div>
  );
}

/** Role-aware Leave tab content embedded inside Attendance page. */
export function LeaveTab() {
  const { role, employeeId } = useAuth();

  if (role === "admin") {
    return (
      <div className="space-y-6">
        <LeaveReviewPanel />
        <AdminLeaveList />
      </div>
    );
  }

  if (role === "manager") {
    return (
      <div className="space-y-6">
        <LeaveReviewPanel employeeId={employeeId ?? undefined} />
        <div>
          <h3 className="mb-3 text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            My leave history
          </h3>
          <LeaveHistory employeeId={employeeId ?? undefined} />
        </div>
      </div>
    );
  }

  return <LeaveHistory employeeId={employeeId ?? undefined} />;
}
