/**
 * Benchmark exception rules for the Daily Work Report activity form — the
 * client-side mirror of backend `activity_master/benchmark_exception.py`.
 *
 * ONE exception exists in Phase 1: NO_FURTHER_AVAILABLE_WORK, "I completed
 * every tag that was actually available, but fewer existed than the target."
 * Ticking it does NOT change the count the employee entered; the real number is
 * what gets saved and exported. It only records WHY that number fell short, so
 * the benchmark report can evaluate the row as achieved.
 *
 * Everything here is pure so `node --test` can pin it without a component
 * harness: the editor calls these helpers, it does not re-implement the rules.
 * The backend re-validates independently and clears anything that does not
 * hold — this module makes the UI honest, it is not the enforcement.
 *
 * Widening past TAGS later means adding to EXCEPTION_ELIGIBLE_COUNT_FIELDS here
 * and to the matching set on the backend; no other logic below names a unit.
 */
import type { BenchmarkType, RelevantCountField } from "../activity-master/types.ts";

/** The stored value. Kept as a const rather than a bare string so the form,
 *  the payload converter and the tests can never drift apart on spelling. */
export const BENCHMARK_EXCEPTION_NO_FURTHER_AVAILABLE_WORK =
  "NO_FURTHER_AVAILABLE_WORK";

export type BenchmarkExceptionCode =
  typeof BENCHMARK_EXCEPTION_NO_FURTHER_AVAILABLE_WORK;

/** Pure per-day numeric modes only. TASK_WITH_QUANTITY carries a quantity but
 *  is a TASK mode — it is deadline work, is excluded from the benchmark Excel
 *  entirely, and can never carry an exception. */
const EXCEPTION_ELIGIBLE_BENCHMARK_TYPES = new Set<BenchmarkType>([
  "NUMERIC",
  "NUMERIC_DAILY",
]);

/** Phase 1: TAGS only. Docs / BOM / Spares / Pages / Records are deliberately
 *  out of scope until the same rule is agreed for them. */
const EXCEPTION_ELIGIBLE_COUNT_FIELDS = new Set<RelevantCountField>(["tags"]);

/** The checkbox label and its helper line — one definition, so the form and
 *  any future surface word it identically. */
export const EXCEPTION_CHECKBOX_LABEL =
  "No further tags were available for this activity";
export const EXCEPTION_CHECKBOX_HELP =
  "Select this only when all available tags for this activity have been completed.";
/** Shown once the box is ticked, so the employee sees the consequence before
 *  saving. Uppercase by design - it mirrors the wording of the report. */
export const EXCEPTION_CONFIRMATION =
  "AVAILABLE WORK COMPLETED - THIS ENTRY WILL BE EVALUATED AS TARGET ACHIEVED.";

/**
 * The entered count as a number, or null when the field is empty or not a
 * usable count. "" / "  " / "abc" / "-3" are all null: no actual has been
 * entered, so there is nothing to except. 0 IS a real entry ("none were
 * available") and comes back as 0.
 */
export function parseActual(raw: string | number | null | undefined): number | null {
  if (raw === null || raw === undefined) return null;
  if (typeof raw === "number") {
    return Number.isFinite(raw) && raw >= 0 ? raw : null;
  }
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const n = Number(trimmed);
  if (!Number.isFinite(n) || n < 0) return null;
  return n;
}

export interface ExceptionVisibilityInput {
  /** The selected sub-activity's benchmark mode. */
  benchmarkType: BenchmarkType | null | undefined;
  /** The selected sub-activity's measured unit. */
  countField: RelevantCountField | null | undefined;
  /** The EFFECTIVE target for this row (base value x the period fraction) —
   *  the same number the row displays and the backend will freeze. */
  target: number | null | undefined;
  /** The raw form value of the actual count input. */
  actual: string | number | null | undefined;
}

/**
 * Whether the "no further tags" checkbox may be shown for this row. All five
 * approved conditions, in one place:
 *
 *   1. the benchmark mode is a pure numeric one;
 *   2. the measured unit is exception-eligible (Phase 1: TAGS);
 *   3. a valid, positive target exists;
 *   4. an actual has been entered;
 *   5. that actual is strictly below the target.
 *
 * Anything else hides it — including a task-mode activity, a Docs/BOM/Spares/
 * Pages/Records activity, an empty or invalid count, and a count that already
 * reached or passed the target (which needs no exception).
 */
export function canShowNoFurtherWorkException(
  input: ExceptionVisibilityInput,
): boolean {
  const { benchmarkType, countField, target } = input;
  if (benchmarkType == null || !EXCEPTION_ELIGIBLE_BENCHMARK_TYPES.has(benchmarkType)) {
    return false;
  }
  if (countField == null || !EXCEPTION_ELIGIBLE_COUNT_FIELDS.has(countField)) {
    return false;
  }
  if (target == null || !Number.isFinite(target) || target <= 0) return false;
  const actual = parseActual(input.actual);
  if (actual === null) return false;
  return actual < target;
}

/**
 * The exception value the row should hold, given what is currently selected and
 * entered. Returns null whenever the checkbox may not be shown, which is what
 * makes every "clears automatically" rule fall out of one function rather than
 * a scatter of effects:
 *
 *   - the activity or sub-activity changed          -> new type/unit/target
 *   - the benchmark changed                         -> new target
 *   - the actual reached or passed the target       -> condition 5 fails
 *   - the actual was emptied or made invalid        -> condition 4 fails
 *   - the row became task-based or non-TAGS         -> conditions 1-2 fail
 *
 * `current` is preserved only while it is still legitimate, so a saved
 * exception survives an unrelated edit but never outlives its own conditions.
 */
export function resolveExceptionCode(
  input: ExceptionVisibilityInput,
  current: string | null | undefined,
): BenchmarkExceptionCode | null {
  if (current !== BENCHMARK_EXCEPTION_NO_FURTHER_AVAILABLE_WORK) return null;
  return canShowNoFurtherWorkException(input)
    ? BENCHMARK_EXCEPTION_NO_FURTHER_AVAILABLE_WORK
    : null;
}
