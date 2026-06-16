export type BenchmarkType = "NUMERIC" | "TASK_BASED";
export type RelevantCountField = "tags" | "docs" | "bom" | "spares";

export interface ActivityMaster {
  id: string;
  parent_id: string | null;
  code: string | null;
  name: string;
  level: "activity" | "sub_activity";
  benchmark_type: BenchmarkType | null;
  benchmark_value: number | null;
  benchmark_period_days: number | null;
  benchmark_unit_note: string | null;
  benchmark_remarks: string | null;
  relevant_count_field: RelevantCountField | null;
  is_active: boolean;
  sort_order: number;
  created_at: string;
}

/** Leaf rows flattened with the parent Activity's name — used for the
 * Daily Work Report's cascading Activity / Sub-Activity selects. */
export interface SubActivityFlat {
  id: string;
  activity_id: string;
  activity_name: string;
  name: string;
  benchmark_type: BenchmarkType | null;
  benchmark_value: number | null;
  benchmark_period_days: number | null;
  relevant_count_field: RelevantCountField | null;
  is_active: boolean;
}
