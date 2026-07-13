"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, CalendarDays, Check, ChevronDown, ChevronRight, Download } from "lucide-react";
import { toast } from "sonner";

import { Pagination } from "@/components/data/pagination";
import { SearchInput } from "@/components/data/search-input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import { weekStartISO } from "@/features/dashboard/utils";
import { formatInt } from "@/lib/format";
import { useUrlState } from "@/lib/use-url-state";

import { downloadPendingBenchmarkXlsx } from "../api";
import { useEmployeesPerformance } from "../hooks";
import type { BenchmarkCycle, EmployeePerformanceRow, PerformanceSort } from "../types";

const PAGE_SIZE = 7;
const COLLAPSE_KEY = "employeePerformanceCollapsed";

// Status filter — client-side, derived from each row's Pending value (the same
// rule the Status badge uses). "all" shows everyone.
type StatusFilter = "all" | "needs_review" | "on_track";

/** True when the employee has pending work (→ "Needs Review", else "On Track"). */
function needsReview(pending: string): boolean {
  return Number(pending) > 0;
}

const MONTHS_SHORT = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

/**
 * Status is derived solely from the employee's Pending value: zero pending →
 * "On Track", any pending → "Needs Review". Rendered with the shared Badge so
 * it matches the rest of the dashboard (success = green pill, danger = red).
 */
function StatusBadge({ pending }: { pending: string }) {
  if (needsReview(pending)) {
    return (
      <Badge variant="danger">
        <AlertTriangle className="h-3 w-3" aria-hidden />
        Needs Review
      </Badge>
    );
  }
  return (
    <Badge variant="success">
      <Check className="h-3 w-3" aria-hidden />
      On Track
    </Badge>
  );
}

/**
 * Compact label for a benchmark cycle — Friday → Thursday, anchored to IST
 * via `weekStartISO()`; "previous" is the completed cycle one week back.
 * Handles a cycle that spans two months ("JUN 26 – JUL 2").
 */
function cycleRangeLabel(cycle: BenchmarkCycle): string {
  const [y, m, d] = weekStartISO().split("-").map(Number);
  const offset = cycle === "previous" ? -7 : 0;
  const fri = new Date(y, m - 1, d + offset);
  const thu = new Date(y, m - 1, d + offset + 6);
  if (fri.getMonth() === thu.getMonth()) {
    return `${MONTHS_SHORT[fri.getMonth()]} ${fri.getDate()}–${thu.getDate()}`;
  }
  return `${MONTHS_SHORT[fri.getMonth()]} ${fri.getDate()} – ${MONTHS_SHORT[thu.getMonth()]} ${thu.getDate()}`;
}

/**
 * Employee Performance — the primary PM comparison surface. Comparison columns
 * only (Employee | Target | Actual | Productivity | Pending). Clicking a row
 * navigates straight to the employee detail route. The whole section is a
 * collapsible panel whose state persists in localStorage. Expand/collapse
 * animates to a measured pixel height (matching the employee dashboard's
 * "Benchmark Activities" card) with a ChevronRight → ChevronDown toggle.
 */
export function PerformanceTable() {
  const router = useRouter();
  // Search / sort / status / cycle / page all persist in the URL so returning
  // from an employee detail page restores the exact view. Namespaced (pf_*) to
  // avoid colliding with anything else on the dashboard URL. Default ordering:
  // the employees with the most pending work surface first so the PM sees who
  // needs attention at a glance (highest pending → lowest).
  const [search, setSearch] = useUrlState("pf_q", "");
  const [pageStr, setPageStr] = useUrlState("pf_page", "1");
  const [sortRaw, setSortRaw] = useUrlState("pf_sort", "pending");
  const [orderRaw, setOrderRaw] = useUrlState("pf_order", "desc");
  const [statusRaw, setStatusFilter] = useUrlState("pf_status", "all");
  // Fri..Thu benchmark window — defaults to the current (live) cycle for
  // viewing; "previous" lets the PM review/export the finished cycle.
  const [cycleRaw, setCycleRaw] = useUrlState("pf_cycle", "current");
  const [exporting, setExporting] = React.useState(false);

  const page = Math.max(1, Number(pageStr) || 1);
  const setPage = (n: number) => setPageStr(String(n));
  const sort = sortRaw as PerformanceSort;
  const order = orderRaw as "asc" | "desc";
  const statusFilter = statusRaw as StatusFilter;
  const cycle = cycleRaw as BenchmarkCycle;

  // Collapse state: default expanded on first visit, then persisted. Read in an
  // effect (not in the initializer) so server and first client render agree.
  const [collapsed, setCollapsed] = React.useState(false);
  React.useEffect(() => {
    if (localStorage.getItem(COLLAPSE_KEY) === "true") setCollapsed(true);
  }, []);

  function toggleCollapsed() {
    setCollapsed((c) => {
      const next = !c;
      localStorage.setItem(COLLAPSE_KEY, String(next));
      return next;
    });
  }

  const { data, isLoading } = useEmployeesPerformance({
    page,
    page_size: PAGE_SIZE,
    search,
    sort,
    order,
    cycle,
  });

  function onSearch(value: string) {
    setSearch(value);
    setPage(1);
  }

  function onCycleChange(next: BenchmarkCycle) {
    setCycleRaw(next);
    setPage(1);
  }

  async function onExport() {
    setExporting(true);
    try {
      await downloadPendingBenchmarkXlsx(cycle);
    } catch {
      toast.error("Export failed. Please try again.");
    } finally {
      setExporting(false);
    }
  }

  function toggleSort(key: PerformanceSort) {
    if (sort === key) {
      setOrderRaw(order === "asc" ? "desc" : "asc");
    } else {
      setSortRaw(key);
      setOrderRaw(key === "name" ? "asc" : "desc");
    }
    setPage(1);
  }

  const rows = data?.items ?? [];
  const total = data?.total ?? 0;

  // Status filter runs client-side on the loaded rows so it's instant and needs
  // no backend change. It stacks with the (server-side) search: rows already
  // match the search query, and we further narrow them by status here.
  const visibleRows = React.useMemo(() => {
    if (statusFilter === "all") return rows;
    const want = statusFilter === "needs_review";
    return rows.filter((row) => needsReview(row.pending) === want);
  }, [rows, statusFilter]);

  // Measure the content so expand/collapse animates to an exact pixel height
  // (same approach as the "Benchmark Activities" card). The content stays
  // mounted while collapsed — clipped to height 0 — so it can be re-measured
  // as search/pagination change it. A ResizeObserver keeps the height in sync.
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const [contentHeight, setContentHeight] = React.useState<number>();
  React.useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const measure = () => setContentHeight(el.offsetHeight);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [visibleRows, isLoading]);

  return (
    <Card className="overflow-hidden">
      <CardHeader
        className={`flex-row items-center justify-between gap-3 space-y-0 px-5 py-3.5 ${
          collapsed ? "" : "border-b border-border"
        }`}
        role="button"
        tabIndex={0}
        aria-expanded={!collapsed}
        onClick={toggleCollapsed}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            toggleCollapsed();
          }
        }}
        style={{ cursor: "pointer" }}
      >
        <CardTitle className="flex items-center gap-1.5 text-base">
          {collapsed ? (
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
          )}
          Employee performance{total > 0 ? ` (${total})` : ""}
        </CardTitle>
      </CardHeader>

      <div
        className="overflow-hidden transition-[height] duration-300 ease-out motion-reduce:transition-none"
        style={{ height: collapsed ? 0 : contentHeight }}
      >
        <div ref={scrollRef}>
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
            <div className="flex items-center gap-2">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    aria-label="Select benchmark cycle"
                    className="inline-flex h-9 items-center gap-2 rounded-md border border-input bg-card px-3 text-sm shadow-sm transition-colors hover:bg-secondary"
                  >
                    <CalendarDays className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="text-muted-foreground">
                      {cycle === "current" ? "This week" : "Previous week"}
                    </span>
                    <span className="font-semibold tabular text-foreground">
                      {cycleRangeLabel(cycle)}
                    </span>
                    <span className="text-xs text-muted-foreground">Fri–Thu</span>
                    <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  {(["current", "previous"] as const).map((option) => (
                    <DropdownMenuItem key={option} onSelect={() => onCycleChange(option)}>
                      <div className="flex-1">
                        <div className="font-medium">
                          {option === "current" ? "Current Week" : "Previous Week"}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {cycleRangeLabel(option)} · Fri–Thu
                        </div>
                      </div>
                      {cycle === option && (
                        <Check className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                      )}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
              <Button onClick={onExport} disabled={exporting}>
                <Download className="h-4 w-4" />
                {exporting ? "Exporting…" : "Export Full Cycle Report"}
              </Button>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <SearchInput
                value={search}
                onChange={onSearch}
                placeholder="Search name or code…"
                className="w-56"
              />
              <Select
                value={statusFilter}
                onValueChange={(value) => setStatusFilter(value as StatusFilter)}
              >
                <SelectTrigger className="w-[150px]" aria-label="Filter by status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="needs_review">Needs Review</SelectItem>
                  <SelectItem value="on_track">On Track</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {isLoading && rows.length === 0 ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-9 w-full" />
              ))}
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <SortHead label="Employee" k="name" sort={sort} order={order} onSort={toggleSort} />
                    <TableHead className="text-right">Target</TableHead>
                    <TableHead className="text-right">Actual</TableHead>
                    <SortHead label="Pending" k="pending" sort={sort} order={order} onSort={toggleSort} align="right" />
                    <TableHead className="text-right">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visibleRows.map((row) => (
                    <Row
                      key={row.id}
                      row={row}
                      onClick={() => router.push(`/dashboard/employees/${row.id}`)}
                    />
                  ))}
                  {visibleRows.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                        No employees match.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
              <Pagination
                total={total}
                limit={PAGE_SIZE}
                offset={(page - 1) * PAGE_SIZE}
                onPageChange={(offset) => setPage(Math.floor(offset / PAGE_SIZE) + 1)}
              />
            </>
          )}
        </div>
      </div>
    </Card>
  );
}

function Row({ row, onClick }: { row: EmployeePerformanceRow; onClick: () => void }) {
  return (
    <TableRow className="cursor-pointer" onClick={onClick}>
      <TableCell className="font-medium">
        {row.name}
        <span className="ml-2 text-xs tabular text-muted-foreground">{row.employee_code}</span>
      </TableCell>
      <TableCell className="tabular text-right">{formatInt(row.target)}</TableCell>
      <TableCell className="tabular text-right">{formatInt(row.actual)}</TableCell>
      <TableCell className="tabular text-right">{formatInt(row.pending)}</TableCell>
      <TableCell className="text-right">
        <div className="flex justify-end">
          <StatusBadge pending={row.pending} />
        </div>
      </TableCell>
    </TableRow>
  );
}

function SortHead({
  label,
  k,
  sort,
  order,
  onSort,
  align,
}: {
  label: string;
  k: PerformanceSort;
  sort: PerformanceSort;
  order: "asc" | "desc";
  onSort: (k: PerformanceSort) => void;
  align?: "right";
}) {
  const active = sort === k;
  return (
    <TableHead className={align === "right" ? "text-right" : undefined}>
      <button
        type="button"
        onClick={() => onSort(k)}
        className="inline-flex items-center gap-1 transition-colors hover:text-foreground"
      >
        {label}
        {active && <span aria-hidden>{order === "asc" ? "↑" : "↓"}</span>}
      </button>
    </TableHead>
  );
}
