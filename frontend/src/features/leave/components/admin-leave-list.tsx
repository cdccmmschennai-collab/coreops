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
import { PermissionStatusBadge } from "@/features/permissions/components/permission-status-badge";
import { useUrlState } from "@/lib/use-url-state";

import {
  allRequestActor,
  allRequestDetailHref,
  allRequestTypeLabel,
  type AllRequestStatus,
} from "../all-requests";
import { useAllRequests } from "../hooks";
import { LeaveStatusBadge } from "./leave-status-badge";

const LIMIT = 20;
const ALL = "__all__";

/** The five statuses both kinds share, so one filter serves the whole table. */
const STATUS_OPTIONS: { value: AllRequestStatus | ""; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "cancellation_requested", label: "Cancellation Requested" },
  { value: "cancelled", label: "Cancelled" },
];

interface Props {
  /** True only when this panel is reused inside a Project Head's "Team
   *  approvals" tab — excludes the Head's own requests from All Requests, same
   *  as the other three queues. */
  excludeSelf?: boolean;
}

/** The "All Requests" tab: leave AND permission history, one filtered table.
 *
 *  IT WAS "ALL LEAVE" UNTIL PHASE 4F, and everything about how it is addressed
 *  is deliberately unchanged — the tab is still `queue=all`, the filters are
 *  still `ls` / `lf` / `lt` / `lo`, and the row still hands the detail page this
 *  list's own live address. Only the label and the rows changed, so an existing
 *  bookmark, a Back navigation and the round trip through a detail page all keep
 *  working exactly as they did.
 *
 *  ONE CALL, NOT TWO MERGED HERE. `GET /all-requests` returns both kinds already
 *  scoped, filtered, sorted and paged (see `backend/app/modules/leave/
 *  all_requests.py`). Two independently paged lists cannot be merged into one
 *  correctly paged list in the browser, and the way that fails is by silently
 *  dropping rows — which is the one thing a history view must not do.
 *
 *  WHICH ROWS EACH READER SEES IS NOT DECIDED HERE. Each kind keeps its own
 *  server-side authorisation: a project manager sees everything, a Project Head
 *  sees their own rows plus those routed to a project THEY head, and nobody
 *  else's. Nothing is filtered client-side.
 *
 *  Filters live in the URL through `useUrlState`, the SAME mechanism the queue
 *  tab strip above this panel uses. That is not a preference: this list used to
 *  write the URL with `router.replace` built from Next's `useSearchParams`,
 *  which never sees the `history.replaceState` `useUrlState` performs - so
 *  picking a status here rebuilt the address from a snapshot that no longer had
 *  `queue=all` in it and threw the reader back to the Pending queue. One
 *  mechanism, and the two cannot disagree. */
export function AdminLeaveList({ excludeSelf = false }: Props) {
  const router = useRouter();
  const { byId: empById } = useEmployeeOptions();

  const [status, setStatus] = useUrlState("ls", "");
  const [employeeId] = useUrlState("le", "");
  // The absence window. Either end may stand alone.
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

  const query = useAllRequests({
    status: status as AllRequestStatus | "",
    employee_id: employeeId || undefined,
    // Sent to the API, not applied here: the list is paged, so a window filtered
    // in the browser would only ever filter the 20 rows this page happens to
    // hold. A leave matches the window by OVERLAP, a permission by its single
    // date — each kind keeps the meaning its own list has always given these
    // two parameters.
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
        <EmptyState title="No requests" description="No requests match the current filters." />
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
                    cancelled and pending rows, of both kinds. */}
                <TableHead>By</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((req) => (
                <TableRow
                  key={`${req.kind}-${req.id}`}
                  className="cursor-pointer hover:bg-muted/40"
                  // A leave row opens Leave Detail, a permission row opens
                  // Permission Detail - the same two pages their own queues
                  // open, so no third layout exists to keep in step.
                  //
                  // Both carry THIS list's own live address - queue, status,
                  // date window, page - so the detail page's back link comes
                  // back to All Requests exactly as it was left. Read from
                  // `window.location` rather than `useSearchParams` because the
                  // filters above are written with `history.replaceState`, which
                  // Next's snapshot does not see.
                  onClick={() =>
                    router.push(
                      allRequestDetailHref(
                        req,
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
                  <TableCell>{allRequestTypeLabel(req)}</TableCell>
                  {/* A permission is a single day, so its two cells hold the
                      same date - the shape the table already had, filled
                      honestly rather than left blank. */}
                  <TableCell className="tabular">{req.from_date}</TableCell>
                  <TableCell className="tabular">{req.to_date}</TableCell>
                  <TableCell>
                    {req.kind === "leave" ? (
                      <LeaveStatusBadge status={req.status} />
                    ) : (
                      <PermissionStatusBadge status={req.status} />
                    )}
                  </TableCell>
                  <TableCell className="max-w-[160px] truncate text-muted-foreground">
                    {req.reason ?? "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {allRequestActor(req) ?? "—"}
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
