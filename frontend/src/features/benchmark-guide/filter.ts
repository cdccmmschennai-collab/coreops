/**
 * Pure search / sort / numbering pipeline for the Benchmark Guide table.
 *
 * `buildGuideRows` takes the rows the API returned (SubActivityFlat[]) plus the
 * current filter state and produces the exact, ordered, numbered rows the table
 * renders. It is deliberately data-in / data-out with NO hardcoded activities —
 * a row only appears because it was in the input, so a newly returned API
 * activity shows up with no code change, and an updated benchmark value flows
 * straight through on the next refetch.
 *
 * Ordering is deterministic: Activity name, then Sub-Activity name (case
 * -insensitive), never database insertion order. SL.No is assigned last, after
 * filtering and sorting.
 */
import type { RelevantCountField, SubActivityFlat } from "../activity-master/types";

// Relative .ts value import — see the note in format.ts (node --test harness).
import { formatBenchmark, resolveModeKey, type BenchmarkModeKey } from "./format.ts";

export interface GuideRow {
  id: string;
  no: number;
  activityName: string;
  subActivityName: string;
  benchmark: string;
  /** True when `benchmark` is a right-alignable number (drives tabular styling). */
  isNumeric: boolean;
  unitPeriod: string;
  /** Short visible mode label. */
  mode: string;
  /** Full technical description for the Mode cell's tooltip / aria-label. */
  modeDescription: string;
  remarks: string;
  // Raw discriminators kept for the compact Unit / Mode filters.
  unitField: RelevantCountField | null;
  modeKey: BenchmarkModeKey;
}

export interface GuideFilters {
  /** Matches ONLY the parent activity name (case-insensitive substring). */
  activitySearch?: string;
  /** Matches ONLY the sub-activity name (case-insensitive substring). */
  subActivitySearch?: string;
  unit?: RelevantCountField | "all";
  mode?: BenchmarkModeKey | "all";
}

/** Case-insensitive, whitespace-tolerant sort/compare helper. */
function cmp(a: string, b: string): number {
  return a.localeCompare(b, undefined, { sensitivity: "base", numeric: true });
}

/**
 * "Showing 24 of 146 sub-activities" — `total` is the authorized, active rows
 * the API returned (before any local search/filter), `visible` is what survives
 * the searches + Unit/Mode filters. The noun agrees with `total`, so a
 * single-row master reads "…of 1 sub-activity". Never counts rows the API never
 * returned (unauthorized / inactive).
 */
export function resultCountLabel(visible: number, total: number): string {
  const noun = total === 1 ? "sub-activity" : "sub-activities";
  return `Showing ${visible} of ${total} ${noun}`;
}

export function buildGuideRows(
  rows: SubActivityFlat[],
  filters: GuideFilters = {},
): GuideRow[] {
  // Two independent searches, combined with AND. Activity Search never matches
  // a sub-activity name (so "FMTL" won't surface TRAINING -> FMTL-FAMILIARIZATION),
  // and Sub-Activity Search never matches the parent name. Unit/Mode text is not
  // searchable — those are the separate dropdown filters.
  const aq = (filters.activitySearch ?? "").trim().toLocaleLowerCase();
  const sq = (filters.subActivitySearch ?? "").trim().toLocaleLowerCase();
  const unit = filters.unit ?? "all";
  const mode = filters.mode ?? "all";

  const filtered = rows.filter((row) => {
    if (unit !== "all" && row.relevant_count_field !== unit) return false;
    if (mode !== "all" && resolveModeKey(row.benchmark_type) !== mode) return false;
    if (aq && !row.activity_name.toLocaleLowerCase().includes(aq)) return false;
    if (sq && !row.name.toLocaleLowerCase().includes(sq)) return false;
    return true;
  });

  filtered.sort(
    (a, b) => cmp(a.activity_name, b.activity_name) || cmp(a.name, b.name),
  );

  return filtered.map((row, i) => {
    const f = formatBenchmark(row);
    return {
      id: row.id,
      no: i + 1,
      activityName: row.activity_name,
      subActivityName: row.name,
      benchmark: f.benchmark,
      isNumeric: f.isNumericBenchmark,
      unitPeriod: f.unitPeriod,
      mode: f.mode,
      modeDescription: f.modeDescription,
      remarks: f.remarks,
      unitField: row.relevant_count_field,
      modeKey: resolveModeKey(row.benchmark_type),
    };
  });
}
