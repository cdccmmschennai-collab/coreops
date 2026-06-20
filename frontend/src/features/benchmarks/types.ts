// Decimal-backed fields (pending, productivity_pct) come over the wire as
// numeric strings (pydantic Decimal -> JSON string, e.g. "50.00") — parse
// with Number()/parseFloat() before display.

export type BenchmarkUnit = "tags" | "docs" | "bom" | "spares";

// One row = one day's actual/target/pending for one NUMERIC sub-activity.
// Only days with pending > 0 are included — a clean day doesn't appear
// here, though it still counts toward the weekly productivity %. A day
// with no submission at all still produces a row (actual="0") so a
// no-show day counts against pending too.
export interface DailyBenchmarkRow {
  date: string;
  sub_activity_id: string;
  activity_name: string | null;
  sub_activity_name: string;
  project_name: string | null;
  project_code: string | null;
  hours_minutes: number;
  actual: string;
  target: string;
  pending: string;
  benchmark_unit: BenchmarkUnit | null;
}

export interface OverdueActivity {
  work_report_task_id: string;
  activity_name: string | null;
  sub_activity_name: string;
  due_date: string;
  days_overdue: number;
}

export type TaskStatus = "pending" | "due_today" | "completed";

export interface TaskStatusRow {
  work_report_task_id: string;
  activity_name: string | null;
  sub_activity_name: string;
  project_name: string | null;
  project_code: string | null;
  report_date: string;
  due_date: string;
  completed_date: string | null;
  hours_minutes: number;
  status: TaskStatus;
  days_overdue: number;
}

export interface MyAlertsSummary {
  pending_benchmarks_count: number;
  overdue_activities_count: number;
  productivity_pct: string | null;
}

export interface MyAlerts {
  shortfalls: DailyBenchmarkRow[];
  daily: DailyBenchmarkRow[];
  overdue: OverdueActivity[];
  tasks: TaskStatusRow[];
  summary: MyAlertsSummary;
}

// ── PM team views (GET /benchmarks/team-alerts, project_manager only) ──────────

// One employee's weekly benchmark rollup — the PM "compare performance" row.
// productivity_pct is null when the employee logged no NUMERIC work this week.
export interface TeamComparisonRow {
  employee_id: string;
  employee_name: string;
  target: string;
  actual: string;
  pending: string;
  productivity_pct: string | null;
}

export interface TeamBacklogRow {
  employee_id: string;
  employee_name: string;
  date: string;
  activity_name: string | null;
  sub_activity_name: string;
  actual: string;
  target: string;
  pending: string;
  benchmark_unit: BenchmarkUnit | null;
}

export interface TeamOverdueRow {
  employee_id: string;
  employee_name: string;
  activity_name: string | null;
  sub_activity_name: string;
  due_date: string;
  days_overdue: number;
}

export interface TeamKpis {
  total_employees: number;
  weekly_productivity_pct: string | null;
  total_pending_benchmarks: number;
  total_overdue_activities: number;
}

export interface TeamAlerts {
  comparison: TeamComparisonRow[];
  backlog: TeamBacklogRow[];
  overdue: TeamOverdueRow[];
  kpis: TeamKpis;
}
