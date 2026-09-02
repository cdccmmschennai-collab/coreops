"use client";

import { useSearchParams, usePathname, useRouter } from "next/navigation";

import { Pagination } from "@/components/data/pagination";
import { EmptyState } from "@/components/feedback/empty-state";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
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
import { useEmployeeOptions } from "@/features/attendance/employee-options";

import { useLeaveList } from "../hooks";
import { LEAVE_CLASSIFICATION_LABEL } from "../types";
import type { LeaveStatus } from "../types";
import { LeaveStatusBadge } from "./leave-status-badge";

const LIMIT = 20;
const ALL = "__all__";

const STATUS_OPTIONS: { value: LeaveStatus | ""; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "cancellation_requested", label: "Cancellation Requested" },
  { value: "cancelled", label: "Cancelled" },
];

interface Props {
  /** True only when this panel is reused inside a Project Head's "Team
   *  approvals" tab — excludes the Head's own requests from the "All leave"
   *  queue, same as the other two queues. */
  excludeSelf?: boolean;
}

/** Admin-level full leave list with filters — the "All leave" queue. */
export function AdminLeaveList({ excludeSelf = false }: Props) {
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

  const query = useLeaveList({
    status,
    employee_id: employeeId || undefined,
    limit: LIMIT,
    offset,
    exclude_self: excludeSelf,
  });
  const items = query.data?.items ?? [];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <Select value={status || ALL} onValueChange={(v) => patch("ls", v === ALL ? "" : v)}>
          <SelectTrigger className="w-52">
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
                    {req.employee_name ??
                      empById.get(req.employee_id) ??
                      req.employee_id.slice(0, 8)}
                  </TableCell>
                  <TableCell>{LEAVE_CLASSIFICATION_LABEL[req.classification]}</TableCell>
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
