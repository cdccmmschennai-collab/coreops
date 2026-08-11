/**
 * The effective per-period benchmark target — the client-side mirror of backend
 * `activity_master/service.py::scaled_target`.
 *
 * Targets count real things (tags, documents, BOM lines), so a scaled target is
 * always a whole number. Half of a 35-tag benchmark is 17.5, and there is no
 * such thing as half a tag, so the half-day target is 18: the employee is asked
 * for whole work, and the rounding favours the benchmark rather than quietly
 * discounting it. A target that divides evenly is untouched (66 -> 33).
 *
 * Rounding UP, not to nearest: 17.5 -> 18 and 17.1 -> 18 alike. The backend
 * applies the identical rule when it freezes the snapshot at submit, so the
 * number shown beside the input is always the number the report is measured
 * against — in the app and in the benchmark Excel.
 */

/**
 * `base` scaled by a period `fraction` (1 full day, 0.5 per half), rounded up
 * to a whole unit. Returns null when there is no configured target, so callers
 * can distinguish "no benchmark" from "a target of 0".
 *
 * `base` is COERCED rather than type-trusted: the API serialises the Decimal
 * `benchmark_value` as a JSON string ("66.00"), even though SubActivityFlat
 * declares it `number`. Number.isFinite("66.00") is false, so validating before
 * coercing silently turns every real target into null — which is exactly how
 * the displayed target once became "—".
 */
export function scaledTarget(
  base: number | string | null | undefined,
  fraction: number | string,
): number | null {
  if (base == null || base === "") return null;
  const value = Number(base);
  const scale = Number(fraction);
  if (!Number.isFinite(value) || !Number.isFinite(scale)) return null;
  return Math.ceil(value * scale);
}
