"use client";

import * as React from "react";
import { ArrowDown, ArrowUp, Pencil, Search } from "lucide-react";

import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import { Pagination } from "@/components/data/pagination";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { monthKeyLabel } from "@/features/attendance/selected-month";
import { useUrlState } from "@/lib/use-url-state";

import { useLeaveBalances } from "../hooks";
import { formatBalance, type LeaveBalance, type SortDir } from "../types";
import { LeaveBalanceEditDialog } from "./leave-balance-edit-dialog";

const LIMIT = 20;
const COL_COUNT = 5;

interface Props {
  /** The month whose balances the table shows, as `YYYY-MM-01`. The page's
   *  selected month - the same one the KPI cards and the calendar use. There is
   *  deliberately no second month picker here. */
  month: string;
  currentMonth: string;
}

/**
 * The PM's Leave Balance table, for ONE month.
 *
 *   Employee Code & Name | Available Leave | Leave/month | Last Updated | Actions
 *
 * Every figure is the backend ledger's, derived for `month`. The table adds
 * nothing up: `available_leave` is that month's closing balance and
 * `monthly_allocation` is the rate in force for that month, so scrolling back to
 * an earlier month shows the rate people were actually on then rather than the
 * rate they are on now.
 */
export function LeaveBalanceTab({ month, currentMonth }: Props) {
  // Search / sort / page persist in the URL (namespaced lb_*) so switching
  // attendance tabs away and back keeps the same view. The month is NOT
  // namespaced here - it is the page's `att_month`, shared with the calendar.
  const [search, setSearch] = useUrlState("lb_q", "");
  const [sortRaw, setSortDir] = useUrlState("lb_sort", "asc");
  const [offsetStr, setOffsetStr] = useUrlState("lb_offset", "0");
  const sortDir = sortRaw as SortDir;
  const offset = Math.max(0, Number(offsetStr) || 0);
  const setOffset = (o: number) => setOffsetStr(String(o));

  const [rawSearch, setRawSearch] = React.useState(search);
  const [editing, setEditing] = React.useState<LeaveBalance | null>(null);

  // Debounce the search box; reset to the first page on a new query. Skip the
  // first run so a page/search restored from the URL isn't reset on mount.
  const firstRun = React.useRef(true);
  React.useEffect(() => {
    if (firstRun.current) {
      firstRun.current = false;
      return;
    }
    const t = setTimeout(() => {
      setSearch(rawSearch);
      setOffset(0);
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rawSearch]);

  // `month` is part of the params object and therefore of the query key, so each
  // month is its own cache entry and a slow response cannot land in another
  // month's table.
  const query = useLeaveBalances({
    q: search || undefined,
    sort_dir: sortDir,
    month,
    limit: LIMIT,
    offset,
  });
  const items = query.data?.items ?? [];
  const total = query.data?.total ?? 0;
  // The month the ROWS ON SCREEN belong to, echoed by the server on its own
  // response - not the month that has been selected. While a new month is
  // loading, `placeholderData` keeps the previous month's rows visible, and a
  // caption read from the selection would label them with a month they are not.
  // The two flip together instead, and the table dims while it is behind.
  const shownMonth = query.data?.month ?? month;
  const stale = query.isPlaceholderData || shownMonth !== month;

  function toggleSort() {
    setSortDir(sortDir === "asc" ? "desc" : "asc");
    setOffset(0);
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Search by name or code…"
            value={rawSearch}
            onChange={(e) => setRawSearch(e.target.value)}
          />
        </div>
        {/* Which month these balances are. No picker: the month comes from the
            calendar's own Previous/Today/Next, so there is one month control on
            the page and this states what it currently selects. */}
        <div className="text-xs text-muted-foreground">
          Balances for{" "}
          <span className="font-medium text-foreground">{monthKeyLabel(shownMonth)}</span>
          {shownMonth !== currentMonth && " (historical)"}
        </div>
      </div>

      {query.isLoading ? (
        <TableSkeleton rows={6} cols={COL_COUNT} />
      ) : query.isError ? (
        <ErrorState
          title="Couldn't load leave balances"
          message={`The balances for ${monthKeyLabel(month)} could not be loaded.`}
          onRetry={() => void query.refetch()}
        />
      ) : items.length === 0 ? (
        <EmptyState
          title="No employees"
          description="No employees match the current search."
        />
      ) : (
        <div
          className={
            stale ? "space-y-3 opacity-60 transition-opacity" : "space-y-3 transition-opacity"
          }
        >
          <Table>
            <TableHeader>
              <TableRow>
                {/* Code and name in ONE column - they identify one person, and
                    splitting them made the row read as two facts. Sorting stays
                    on this column because the server sorts by name. */}
                <TableHead>
                  <button
                    type="button"
                    onClick={toggleSort}
                    className="inline-flex items-center gap-1 hover:text-foreground"
                  >
                    Employee Code &amp; Name
                    {sortDir === "asc" ? (
                      <ArrowUp className="h-3 w-3" />
                    ) : (
                      <ArrowDown className="h-3 w-3" />
                    )}
                  </button>
                </TableHead>
                <TableHead>Available Leave</TableHead>
                <TableHead>Leave/month</TableHead>
                <TableHead>Last Updated</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((b) => (
                <TableRow key={b.employee_id}>
                  <TableCell>
                    <span className="tabular font-medium">{b.employee_code}</span>
                    <span className="text-muted-foreground"> - </span>
                    <span>{b.employee_name}</span>
                  </TableCell>
                  {/* Zero and negative balances print as themselves; "-" means
                      the month is before this employee's ledger begins, which is
                      not the same as a balance of zero. */}
                  <TableCell className="tabular">
                    {formatBalance(b.available_leave, b.in_ledger)}
                  </TableCell>
                  <TableCell className="tabular">
                    {formatBalance(b.monthly_allocation)}
                  </TableCell>
                  <TableCell className="tabular text-muted-foreground">
                    {/* The backend's timestamp, rendered - never a browser clock
                        and never derived from anything else on the row. */}
                    {b.last_updated ? new Date(b.last_updated).toLocaleDateString() : "-"}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="secondary" onClick={() => setEditing(b)}>
                      <Pencil className="h-3.5 w-3.5" />
                      Edit
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {total > LIMIT && (
            <Pagination
              total={total}
              limit={LIMIT}
              offset={offset}
              onPageChange={setOffset}
            />
          )}
        </div>
      )}

      {editing && (
        // The dialog edits the month the ROW describes (`balance.month`), never
        // the month currently selected - so a click landing while a new month is
        // still loading can never post a correction into the wrong month.
        <LeaveBalanceEditDialog
          balance={editing}
          open={editing !== null}
          onOpenChange={(open) => {
            if (!open) setEditing(null);
          }}
        />
      )}
    </div>
  );
}
