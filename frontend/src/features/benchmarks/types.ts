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
