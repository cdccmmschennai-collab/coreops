// NUMERIC / TASK_BASED are LEGACY values still stored on existing records; they
// stay readable and behave exactly like NUMERIC_DAILY / TASK_STATUS_ONLY
// respectively. New configuration uses the three explicit modes.
export type BenchmarkType =
  | "NUMERIC"
  | "TASK_BASED"
  | "NUMERIC_DAILY"
  | "TASK_STATUS_ONLY"
  | "TASK_WITH_QUANTITY";

export type RelevantCountField =
  | "tags"
  | "docs"
  | "bom"
  | "spares"
  | "pages"
  | "records";

/** Modes carrying a quantity: they need a target + a measurement unit, and they
 *  produce a numeric target/actual/pending/percentage. */
export const QUANTITY_BENCHMARK_TYPES = new Set<BenchmarkType>([
  "NUMERIC",
  "NUMERIC_DAILY",
  "TASK_WITH_QUANTITY",
]);

/** Modes carrying a deadline: they need a period, and they show the completion
 *  checkbox + carry forward until completed. */
export const TASK_BENCHMARK_TYPES = new Set<BenchmarkType>([
  "TASK_BASED",
  "TASK_STATUS_ONLY",
  "TASK_WITH_QUANTITY",
]);

export const isQuantityBenchmark = (t: BenchmarkType | null | undefined): boolean =>
  t != null && QUANTITY_BENCHMARK_TYPES.has(t);

export const isTaskBenchmark = (t: BenchmarkType | null | undefined): boolean =>
  t != null && TASK_BENCHMARK_TYPES.has(t);

/** Selectable modes, in the order the Activity Master form offers them. The two
 *  legacy values are deliberately NOT offered for new records — they remain in
 *  BENCHMARK_TYPE_LABEL so existing records still render a readable label. */
export const SELECTABLE_BENCHMARK_TYPES = [
  "NUMERIC_DAILY",
  "TASK_STATUS_ONLY",
  "TASK_WITH_QUANTITY",
] as const satisfies readonly BenchmarkType[];

/** Every mode the API accepts, including the two legacy values. Form schemas
 *  validate against THIS (an existing record on a legacy mode must still load
 *  and re-save); only the dropdown narrows to SELECTABLE_BENCHMARK_TYPES. */
export const ALL_BENCHMARK_TYPES = [
  "NUMERIC",
  "TASK_BASED",
  "NUMERIC_DAILY",
  "TASK_STATUS_ONLY",
  "TASK_WITH_QUANTITY",
] as const satisfies readonly BenchmarkType[];

export const BENCHMARK_TYPE_LABEL: Record<BenchmarkType, string> = {
  NUMERIC_DAILY: "Numeric daily benchmark",
  TASK_STATUS_ONLY: "Task-based - duration and completion status",
  TASK_WITH_QUANTITY: "Task-based - quantity, duration and completion status",
  // Legacy, read-only: shown on existing records, never offered for new ones.
  NUMERIC: "Numeric daily benchmark (legacy)",
  TASK_BASED: "Task-based - duration and completion status (legacy)",
};

export const COUNT_FIELDS = [
  "tags",
  "docs",
  "bom",
  "spares",
  "pages",
  "records",
] as const satisfies readonly RelevantCountField[];

/** Unit labels for the Activity Master dropdown and the report form. */
export const COUNT_FIELD_LABEL: Record<RelevantCountField, string> = {
  tags: "Tags",
  docs: "Docs",
  bom: "BOM",
  spares: "Spares",
  pages: "Pages",
  records: "Records",
};

/** The work-report form field each unit reads/writes. Mirrors the backend's
 *  COUNT_FIELD_BY_UNIT — a record is not a document, so records never share
 *  docs_count. */
export const COUNT_FIELD_KEY: Record<RelevantCountField, string> = {
  tags: "tags_count",
  docs: "docs_count",
  bom: "bom_count",
  spares: "spares_count",
  pages: "pages_count",
  records: "records_count",
};

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
  /** COMMON (default) / RESTRICTED — the access mode. Meaningful on top-level
   *  activities; sub-activities inherit their parent's. */
  access_type: AccessType;
  created_at: string;
}

export type AccessType = "COMMON" | "RESTRICTED";

/** Leaf rows flattened with the parent Activity's name — used for the
 * Daily Work Report's cascading Activity / Sub-Activity selects.
 *
 * Carries the FULL benchmark configuration: the report form renders the
 * master's own guidance (benchmark_remarks) and measurement unit beside the
 * selection, read-only. */
export interface SubActivityFlat {
  id: string;
  activity_id: string;
  activity_name: string;
  name: string;
  benchmark_type: BenchmarkType | null;
  benchmark_value: number | null;
  benchmark_period_days: number | null;
  // Supplementary display text configured in Activity Master. benchmark_remarks
  // is guidance TO the employee — never the employee's own report remarks, and
  // never editable from the report page.
  benchmark_unit_note: string | null;
  benchmark_remarks: string | null;
  // The real, calculation-driving unit. benchmark_unit_note is free text and is
  // never the unit's source.
  relevant_count_field: RelevantCountField | null;
  is_active: boolean;
}
