"use client";

import * as React from "react";
import { ArrowDown, ArrowUp, Pencil, Search } from "lucide-react";

import { EmptyState } from "@/components/feedback/empty-state";
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

import { useUrlState } from "@/lib/use-url-state";

import { useLeaveBalances } from "../hooks";
import type { LeaveBalance, SortDir } from "../types";
import { LeaveBalanceEditDialog } from "./leave-balance-edit-dialog";

const LIMIT = 20;

export function LeaveBalanceTab() {
  // Search / sort / page persist in the URL (namespaced lb_*) so switching
  // attendance tabs away and back keeps the same view.
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

  const query = useLeaveBalances({
    q: search || undefined,
    sort_dir: sortDir,
    limit: LIMIT,
    offset,
  });
  const items = query.data?.items ?? [];
  const total = query.data?.total ?? 0;

  function toggleSort() {
    setSortDir(sortDir === "asc" ? "desc" : "asc");
    setOffset(0);
  }

  return (
    <div className="space-y-3">
      <div className="relative max-w-xs">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="pl-9"
          placeholder="Search by name or code…"
          value={rawSearch}
          onChange={(e) => setRawSearch(e.target.value)}
        />
      </div>

      {query.isLoading ? (
        <TableSkeleton rows={6} cols={5} />
      ) : items.length === 0 ? (
        <EmptyState
          title="No employees"
          description="No employees match the current search."
        />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Employee Code</TableHead>
                <TableHead>
                  <button
                    type="button"
                    onClick={toggleSort}
                    className="inline-flex items-center gap-1 hover:text-foreground"
                  >
                    Employee Name
                    {sortDir === "asc" ? (
                      <ArrowUp className="h-3 w-3" />
                    ) : (
                      <ArrowDown className="h-3 w-3" />
                    )}
                  </button>
                </TableHead>
                <TableHead>Available Leave</TableHead>
                <TableHead>Last Updated</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((b) => (
                <TableRow key={b.employee_id}>
                  <TableCell className="tabular font-medium">{b.employee_code}</TableCell>
                  <TableCell>{b.employee_name}</TableCell>
                  <TableCell className="tabular">{b.available_leave}</TableCell>
                  <TableCell className="tabular text-muted-foreground">
                    {b.last_updated ? new Date(b.last_updated).toLocaleDateString() : "—"}
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
        </>
      )}

      {editing && (
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
