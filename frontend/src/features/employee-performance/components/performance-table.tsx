"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { CalendarDays, ChevronDown, ChevronRight } from "lucide-react";

import { Pagination } from "@/components/data/pagination";
import { SearchInput } from "@/components/data/search-input";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
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

import { useEmployeesPerformance } from "../hooks";
import type { EmployeePerformanceRow, PerformanceSort } from "../types";

const PAGE_SIZE = 5;
const COLLAPSE_KEY = "employeePerformanceCollapsed";

const MONTHS_SHORT = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

function formatPct(pct: string | null): string {
  return pct == null ? "—" : `${Number(pct).toFixed(0)}%`;
}

/**
 * Compact label for the current working week — Monday → Friday only, anchored
 * to IST via `weekStartISO()`. Handles a week that spans two months
 * ("JUN 29 – JUL 3").
 */
function weekRangeLabel(): string {
  const [y, m, d] = weekStartISO().split("-").map(Number);
  const mon = new Date(y, m - 1, d);
  const fri = new Date(y, m - 1, d + 4);
  if (mon.getMonth() === fri.getMonth()) {
    return `${MONTHS_SHORT[mon.getMonth()]} ${mon.getDate()}–${fri.getDate()}`;
  }
  return `${MONTHS_SHORT[mon.getMonth()]} ${mon.getDate()} – ${MONTHS_SHORT[fri.getMonth()]} ${fri.getDate()}`;
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
  const [search, setSearch] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [sort, setSort] = React.useState<PerformanceSort>("productivity");
  const [order, setOrder] = React.useState<"asc" | "desc">("asc");

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
  });

  function onSearch(value: string) {
    setSearch(value);
    setPage(1);
  }

  function toggleSort(key: PerformanceSort) {
    if (sort === key) {
      setOrder((o) => (o === "asc" ? "desc" : "asc"));
    } else {
      setSort(key);
      setOrder(key === "name" ? "asc" : "desc");
    }
    setPage(1);
  }

  const rows = data?.items ?? [];
  const total = data?.total ?? 0;

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
  }, [rows, isLoading]);

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
            <div className="inline-flex h-9 items-center gap-2 rounded-md border border-input bg-card px-3 text-sm shadow-sm">
              <CalendarDays className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="text-muted-foreground">This week</span>
              <span className="font-semibold tabular text-foreground">{weekRangeLabel()}</span>
              <span className="text-xs text-muted-foreground">Mon–Fri</span>
            </div>
            <SearchInput
              value={search}
              onChange={onSearch}
              placeholder="Search name or code…"
              className="w-56"
            />
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
                    <SortHead label="Productivity" k="productivity" sort={sort} order={order} onSort={toggleSort} align="right" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row) => (
                    <Row
                      key={row.id}
                      row={row}
                      onClick={() => router.push(`/dashboard/employees/${row.id}`)}
                    />
                  ))}
                  {rows.length === 0 && (
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
      <TableCell className="tabular text-right">{formatPct(row.productivity)}</TableCell>
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
