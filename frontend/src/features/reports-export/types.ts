// PM Weekly Activity Report — flat rows (one per Employee + Date). The preview
// renders exactly the same data the Excel export contains.

export interface ActivityCell {
  // Which half of the day the activity belongs to ("first_half" /
  // "second_half" / "full_day"), and that half's own status when a split day
  // mixes two. Read off work_report_periods; drives the Excel HALF column.
  day_part: string | null;
  period_status: string | null;
  project_code: string | null;
  activity_type: string | null;
  sub_activity_type: string | null;
  tags: number;
  docs: number;
  bom: number;
  spares: number;
  pages: number;
  records: number;
  // Benchmark frozen on the task at submit time. The Excel export renders these
  // as "120 TAGS" / "LS" / "LS - 300 SPARES"; never recomputed client-side.
  benchmark_type: string | null;
  benchmark_value: number | null;
  benchmark_unit: string | null;
}

export interface ActivityRow {
  employee_label: string;
  report_date: string;
  day_status: string | null;
  remarks: string | null;
  activities: ActivityCell[];
}

export interface ActivityReport {
  max_activities: number;
  rows: ActivityRow[];
}

export interface ActivityReportFilters {
  employee_id: string;
  project_id: string;
  activity_id: string;
  sub_activity_id: string;
  from: string;
  to: string;
}

export const EMPTY_FILTERS: ActivityReportFilters = {
  employee_id: "",
  project_id: "",
  activity_id: "",
  sub_activity_id: "",
  from: "",
  to: "",
};

export interface ActivityOption {
  id: string;
  name: string;
}

export interface SubActivityOption {
  id: string;
  name: string;
  activity_id: string;
}
