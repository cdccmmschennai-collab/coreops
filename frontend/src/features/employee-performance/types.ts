// Decimal-backed fields (target/actual/pending/productivity) arrive as numeric
// strings (pydantic Decimal -> JSON string); parse with Number() before display.

import type { DailyBenchmarkRow, OverdueActivity } from "@/features/benchmarks/types";

export type PerformanceStatus = "on_track" | "at_risk" | "behind" | "no_data";

/** Full weekly ledger for one employee — fed into computeReconciliation. */
export interface EmployeeBenchmarks {
  daily: DailyBenchmarkRow[];
  overdue: OverdueActivity[];
}

/** Layer 1 — one comparison-table row. Comparison columns ONLY. */
export interface EmployeePerformanceRow {
  id: string;
  name: string;
  employee_code: string;
  target: string;
  actual: string;
  pending: string;
  productivity: string | null;
  status: PerformanceStatus;
}

export interface EmployeesPerformancePage {
  items: EmployeePerformanceRow[];
  total: number;
  page: number;
  page_size: number;
}

/** Layer 2/3 — shared overview aggregation (drawer + Overview tab). */
export interface EmployeeOverview {
  employee_id: string;
  employee_name: string;
  productivity_pct: string | null;
  days_worked_this_week: number;
  completed_benchmarks: number;
  pending_benchmarks: number;
  overdue_activities: number;
}

export type PerformanceSort = "name" | "productivity" | "pending" | "actual" | "target";

/** Status filter — mirrors the Status badge: any pending backlog → "Needs
 * Review", zero → "On Track". "all" shows everyone. Applied server-side (before
 * pagination) so the returned total is the filtered count. */
export type PerformanceStatusFilter = "all" | "needs_review" | "on_track";

/** Fri..Thu benchmark window, as a whole-week offset back from the cycle
 * containing today: 0 = current, 1 = previous, up to MAX_WEEK_OFFSET. Drives
 * both the comparison table and the export, so the two can never disagree.
 *
 * The backend still accepts the legacy "current"/"previous" strings, but the
 * frontend sends the integer only — one representation, one source of truth. */
export type WeekOffset = 0 | 1 | 2 | 3;

export const MAX_WEEK_OFFSET = 3;

export const WEEK_OFFSETS = [0, 1, 2, 3] as const satisfies readonly WeekOffset[];

/** Whether a parsed URL value is a cycle we actually offer. An out-of-range
 * value falls back to the current cycle rather than requesting a period that
 * would be rejected. */
export const isWeekOffset = (value: number): value is WeekOffset =>
  Number.isInteger(value) && value >= 0 && value <= MAX_WEEK_OFFSET;

export const WEEK_OFFSET_LABEL: Record<WeekOffset, string> = {
  0: "Current week",
  1: "Previous week",
  2: "2 weeks ago",
  3: "3 weeks ago",
};

export interface PerformanceParams {
  page: number;
  page_size: number;
  search: string;
  status: PerformanceStatusFilter;
  sort: PerformanceSort;
  order: "asc" | "desc";
  weekOffset: WeekOffset;
}
