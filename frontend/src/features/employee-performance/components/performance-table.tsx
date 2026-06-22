"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, ChevronUp } from "lucide-react";

import { Pagination } from "@/components/data/pagination";
import { SearchInput } from "@/components/data/search-input";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatInt } from "@/lib/format";

import { useEmployeesPerformance } from "../hooks";
import type { EmployeePerformanceRow, PerformanceSort } from "../types";

const PAGE_SIZE = 5;
const COLLAPSE_KEY = "employeePerformanceCollapsed";

function formatPct(pct: string | null): string {
  return pct == null ? "—" : `${Number(pct).toFixed(0)}%`;
}

/**
 * Employee Performance — the primary PM comparison surface. Comparison columns
 * only (Employee | Target | Actual | Productivity | Pending). Clicking a row
 * navigates straight to the employee detail route. The whole section is a
 * collapsible panel whose state persists in localStorage.
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

  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={toggleCollapsed}
        aria-expanded={!collapsed}
        className="flex w-full items-center justify-between gap-3 px-5 py-3.5 text-left"
      >
        <span className="text-base font-semibold">Employee performance</span>
        {collapsed ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      {!collapsed && (
        <div className="flex justify-end border-t border-border px-5 py-3">
          <SearchInput
            value={search}
            onChange={onSearch}
            placeholder="Search name or code…"
            className="w-56"
          />
        </div>
      )}

      {!collapsed &&
        (isLoading && rows.length === 0 ? (
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
        ))}
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
