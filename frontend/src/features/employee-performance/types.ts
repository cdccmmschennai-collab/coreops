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

export interface PerformanceParams {
  page: number;
  page_size: number;
  search: string;
  sort: PerformanceSort;
  order: "asc" | "desc";
}
