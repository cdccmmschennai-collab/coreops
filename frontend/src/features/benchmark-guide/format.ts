/**
 * Pure, human-readable formatting for the Benchmark Guide.
 *
 * Turns a raw Activity Master sub-activity row (the exact shape the Work Report
 * activity selector already consumes) into the four display strings the guide
 * table renders: Benchmark, Unit / Period, Mode, and Remarks. No raw enum or
 * database field name ever reaches the UI.
 *
 * The five benchmark types resolve through the SAME sets the report form uses
 * (isQuantityBenchmark / isTaskBenchmark from activity-master/types), so the two
 * legacy stored values keep behaving exactly like their modern equivalents:
 *   NUMERIC    -> NUMERIC_DAILY      (Numeric Daily)
 *   TASK_BASED -> TASK_STATUS_ONLY   (Task - Completion Only)
 * This module NEVER reads from a hardcoded activity list; every value comes from
 * the row passed in (i.e. from the backend API).
 */
// Relative .ts import (not the @/ alias): these are runtime VALUES, and the
// pure modules here are loaded by the `node --test` harness, which resolves ESM
// strictly and cannot follow the @/ path alias. allowImportingTsExtensions (see
// tsconfig) makes the explicit extension type-check cleanly.
import {
  COUNT_FIELD_LABEL,
  QUANTITY_BENCHMARK_TYPES,
  TASK_BENCHMARK_TYPES,
  type BenchmarkType,
  type RelevantCountField,
  type SubActivityFlat,
} from "../activity-master/types.ts";

/** The four canonical modes the guide groups the five stored types into. */
export type BenchmarkModeKey = "numeric" | "task_quantity" | "task_completion" | "none";

export interface FormattedBenchmark {
  /** Numeric target ("250"), "Lump Sum" for a completion-only task, or "-". */
  benchmark: string;
  /** True when `benchmark` is a right-alignable number (numeric / quantity
   *  modes with a value). "Lump Sum" and "-" are false. */
  isNumericBenchmark: boolean;
  /** "Records / Day", "Pages / Day", "Complete within 2 days", or "-". */
  unitPeriod: string;
  /** Short visible mode label, e.g. "Numeric daily" / "Quantity + completion". */
  mode: string;
  /** Full technical description for tooltip / aria-label, e.g.
   *  "Task - Quantity + Completion". */
  modeDescription: string;
  /** Master notes (+ completion rule) only; "" when there is nothing to add. */
  remarks: string;
}

/** Resolve a stored benchmark_type (incl. the two legacy values) to a mode. */
export function resolveModeKey(type: BenchmarkType | null | undefined): BenchmarkModeKey {
  if (type == null) return "none";
  if (type === "TASK_WITH_QUANTITY") return "task_quantity";
  if (TASK_BENCHMARK_TYPES.has(type)) return "task_completion";
  if (QUANTITY_BENCHMARK_TYPES.has(type)) return "numeric";
  return "none";
}

// Short label shown in the table's Mode column — kept to one/two lines.
const MODE_LABEL_SHORT: Record<BenchmarkModeKey, string> = {
  numeric: "Numeric daily",
  task_quantity: "Quantity + completion",
  task_completion: "Completion only",
  none: "No benchmark",
};

// Full technical description exposed via tooltip / aria-label (title attr).
// ASCII hyphen only (house style) — never an en/em dash.
const MODE_LABEL_FULL: Record<BenchmarkModeKey, string> = {
  numeric: "Numeric Daily",
  task_quantity: "Task - Quantity + Completion",
  task_completion: "Task - Completion Only",
  none: "No benchmark",
};

/** Short visible mode label for the Mode column. */
export function benchmarkModeLabel(type: BenchmarkType | null | undefined): string {
  return MODE_LABEL_SHORT[resolveModeKey(type)];
}

/** Full technical mode description (tooltip / accessible label). */
export function benchmarkModeDescription(type: BenchmarkType | null | undefined): string {
  return MODE_LABEL_FULL[resolveModeKey(type)];
}

/** Whether the row's Benchmark cell renders a right-alignable number (a numeric
 *  or quantity+completion mode that actually carries a value). "Lump Sum" and
 *  the empty "-" placeholder are NOT numeric. Centralized so alignment is
 *  decided in one place, never by sniffing the rendered text per component. */
export function isNumericBenchmark(row: SubActivityFlat): boolean {
  const mode = resolveModeKey(row.benchmark_type);
  if (mode !== "numeric" && mode !== "task_quantity") return false;
  return formatBenchmarkNumber(row.benchmark_value) !== "";
}

/** Title-case unit label ("Tags", "BOM", "Pages"...) or null when no unit. */
export function unitLabel(field: RelevantCountField | null | undefined): string | null {
  return field ? COUNT_FIELD_LABEL[field] : null;
}

/** Format a benchmark value with no trailing zeros: 250 -> "250", 250.5 -> "250.5". */
export function formatBenchmarkNumber(value: number | string | null | undefined): string {
  if (value == null || value === "") return "";
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  return String(Number(n.toFixed(2)));
}

function periodPhrase(days: number | null | undefined): string {
  const n = Math.max(1, days ?? 1);
  return `Complete within ${n} ${n === 1 ? "day" : "days"}`;
}

/**
 * The Remarks cell is the Activity Master Sub-Activity "Remarks" field
 * (benchmark_remarks) — the EXACT trimmed value the business configured, and
 * nothing else. It never mixes in benchmark_unit_note, a work-report day/half
 * remark, or any generated mode/completion sentence. Returns "" when unset; the
 * table renders the empty-cell placeholder.
 */
export function benchmarkRemarks(row: SubActivityFlat): string {
  return (row.benchmark_remarks ?? "").trim();
}

/** The full formatted view of one sub-activity's benchmark. */
export function formatBenchmark(row: SubActivityFlat): FormattedBenchmark {
  const mode = resolveModeKey(row.benchmark_type);
  const ul = unitLabel(row.relevant_count_field);

  let benchmark = "-";
  let unitPeriod = "-";

  if (mode === "numeric" || mode === "task_quantity") {
    const num = formatBenchmarkNumber(row.benchmark_value);
    benchmark = num || "-";
    // The quantity is a per-day production target in both quantity modes.
    unitPeriod = ul ? `${ul} / Day` : "Per day";
  } else if (mode === "task_completion") {
    benchmark = "Lump Sum";
    unitPeriod = periodPhrase(row.benchmark_period_days);
  }

  return {
    benchmark,
    isNumericBenchmark: isNumericBenchmark(row),
    unitPeriod,
    mode: MODE_LABEL_SHORT[mode],
    modeDescription: MODE_LABEL_FULL[mode],
    remarks: benchmarkRemarks(row),
  };
}
