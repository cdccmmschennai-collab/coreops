"use client";

import { useRouter } from "next/navigation";

import { Pagination } from "@/components/data/pagination";
import { EmptyState } from "@/components/feedback/empty-state";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import { Input } from "@/components/ui/input";
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
import { useUrlState } from "@/lib/use-url-state";

import { useLeaveList } from "../hooks";
import {
  LEAVE_CLASSIFICATION_LABEL,
  leaveDecisionActor,
  leaveDetailHref,
} from "../types";
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

/** Admin-level full leave list with filters — the "All leave" queue.
 *
 *  Filters live in the URL through `useUrlState`, the SAME mechanism the queue
 *  tab strip above this panel already uses. That is not a preference: this list
 *  used to write the URL with `router.replace` built from Next's
 *  `useSearchParams`, which never sees the `history.replaceState` `useUrlState`
 *  performs - so picking a status here rebuilt the address from a snapshot that
 *  no longer had `queue=all` in it and threw the reader back to the Pending
 *  queue. One mechanism, and the two cannot disagree.
 *
 *  Every row opens the shared Leave Detail page, carrying this list's own live
 *  address so "← Leave" returns to All leave with these filters intact. */
export function AdminLeaveList({ excludeSelf = false }: Props) {
  const router = useRouter();
  const { byId: empById } = useEmployeeOptions();

  const [status, setStatus] = useUrlState("ls", "");
  const [employeeId] = useUrlState("le", "");
  // The leave-period window. Either end may stand alone.
  const [fromDate, setFromDate] = useUrlState("lf", "");
  const [toDate, setToDate] = useUrlState("lt", "");
  const [rawOffset, setOffset] = useUrlState("lo", "0");
  const offset = Math.max(0, Number(rawOffset) || 0);

  /** Apply a filter and go back to page 1 — the row at offset 60 of the old
   *  result set is not the row at offset 60 of the new one. */
  function filter(apply: () => void) {
    apply();
    setOffset("0");
  }

  const query = useLeaveList({
    status: status as LeaveStatus | "",
    employee_id: employeeId || undefined,
    // Sent to the API, not applied here: the list is paged, so a window filtered
    // in the browser would only ever filter the 20 rows this page happens to
    // hold. `from`/`to` are matched against the LEAVE PERIOD as an overlap by
    // `leave/service.list_leave_requests`.
    from: fromDate || undefined,
    to: toDate || undefined,
    limit: LIMIT,
    offset,
    exclude_self: excludeSelf,
  });
  const items = query.data?.items ?? [];

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <div className="flex items-center gap-1">
          <Input
            type="date"
            className="sm:w-40"
            value={fromDate}
            max={toDate || undefined}
            onChange={(e) => filter(() => setFromDate(e.target.value))}
            aria-label="From date"
          />
          <span className="text-muted-foreground">→</span>
          <Input
            type="date"
            className="sm:w-40"
            value={toDate}
            min={fromDate || undefined}
            onChange={(e) => filter(() => setToDate(e.target.value))}
            aria-label="To date"
          />
        </div>
        <Select
          value={status || ALL}
          onValueChange={(v) => filter(() => setStatus(v === ALL ? "" : v))}
        >
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
        <TableSkeleton rows={5} cols={7} />
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
                {/* "By", not "Approved by": this table also holds rejected,
                    cancelled and pending rows. */}
                <TableHead>By</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((req) => (
                <TableRow
                  key={req.id}
                  className="cursor-pointer hover:bg-muted/40"
                  // Carries THIS list's own live address - queue, status, date
                  // window, page - so "← Leave" on the detail page comes back to
                  // All leave exactly as it was left. Read from
                  // `window.location` rather than `useSearchParams` because the
                  // filters above are written with `history.replaceState`, which
                  // Next's snapshot does not see.
                  onClick={() =>
                    router.push(
                      leaveDetailHref(
                        req.id,
                        `${window.location.pathname}${window.location.search}`,
                      ),
                    )
                  }
                >
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
                  <TableCell className="text-muted-foreground">
                    {leaveDecisionActor(req) ?? "—"}
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
              onPageChange={(o) => setOffset(String(o))}
            />
          )}
        </>
      )}
    </div>
  );
}
