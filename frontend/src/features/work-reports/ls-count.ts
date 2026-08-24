/**
 * Which count unit owns the activity row's MAIN Count input, and which units
 * are therefore left to the "Other counts" section.
 *
 * Two ways a row gets its main unit, and only two:
 *
 *   a QUANTITY mode  (NUMERIC / NUMERIC_DAILY / TASK_WITH_QUANTITY)
 *       Activity Master names it — `relevant_count_field` — because the unit is
 *       part of the benchmark. Unchanged behaviour: the row shows that unit's
 *       input with its target, and the employee cannot repoint it.
 *
 *   a LUMPSUM row    (TASK_STATUS_ONLY / legacy TASK_BASED)
 *       Activity Master names NOTHING (a lumpsum is measured by completion
 *       within a duration), so the employee names it themselves in the dropdown
 *       beside the Count: "Count [25] [Tags]". The number lands in tags_count
 *       exactly like any other count; the picked unit rides along as
 *       `count_field` and is stored in relevant_count_field_snapshot.
 *
 * The rule that keeps the form honest is one line — `otherCountFields` excludes
 * whatever `primaryCountField` returned — so the unit shown in the Count row can
 * never ALSO appear as a second, separate input under "Other counts". Picking
 * Tags in the dropdown moves the Tags input into the Count row; it does not add
 * one.
 *
 * Pure, so `node --test` can pin the rules without a component harness (the
 * editor calls these, it does not re-implement them). The backend enforces the
 * same split independently — see activity_master/models.py
 * `is_lumpsum_unit_row` and work_reports/service.py `_validate_tasks`.
 */
import {
  COUNT_FIELDS,
  COUNT_FIELD_KEY,
  COUNT_FIELD_LABEL,
  isQuantityBenchmark,
  isTaskBenchmark,
} from "../activity-master/types.ts";
import type {
  BenchmarkType,
  RelevantCountField,
} from "../activity-master/types.ts";

/** The form field name for a unit ("tags" -> "tags_count"), typed against the
 *  task row's six count fields. */
export type CountFieldName =
  | "tags_count" | "docs_count" | "bom_count"
  | "spares_count" | "pages_count" | "records_count";

export const countFieldName = (u: RelevantCountField): CountFieldName =>
  COUNT_FIELD_KEY[u] as CountFieldName;

/** Every unit's form field, in the order COUNT_FIELDS declares them. */
export const ALL_COUNT_FIELDS: CountFieldName[] =
  COUNT_FIELDS.map(countFieldName);

/** The Count dropdown's options — derived from COUNT_FIELDS, never a second
 *  hand-written list, so a seventh unit appears here the moment it exists. */
export const COUNT_FIELD_OPTIONS: { value: RelevantCountField; label: string }[] =
  COUNT_FIELDS.map((u) => ({ value: u, label: COUNT_FIELD_LABEL[u] }));

const VALID_COUNT_FIELDS = new Set<string>(COUNT_FIELDS);

/** Narrow a stored/selected string to a real unit. Anything else — "", a stale
 *  value, a hand-edited payload — is treated as "nothing picked" rather than
 *  being passed on to the backend to reject. */
export const asCountField = (
  value: string | null | undefined,
): RelevantCountField | null =>
  value && VALID_COUNT_FIELDS.has(value) ? (value as RelevantCountField) : null;

/**
 * True for a LUMPSUM row: the employee picks the unit because Activity Master
 * configured none. Mirrors backend `is_lumpsum_unit_row` argument for argument
 * — a TASK mode WITH a configured unit (TASK_WITH_QUANTITY) is deliberately not
 * one, since its unit belongs to its benchmark.
 */
export function isLumpsumUnitRow(
  benchmarkType: BenchmarkType | null | undefined,
  relevantCountField: RelevantCountField | null | undefined,
): boolean {
  return isTaskBenchmark(benchmarkType) && !relevantCountField;
}

/** The unit configured by the benchmark, or null. This is the ONLY thing that
 *  drives a target/actual comparison, so it is read from the master and never
 *  from what the employee picked. */
export function benchmarkCountField(
  benchmarkType: BenchmarkType | null | undefined,
  relevantCountField: RelevantCountField | null | undefined,
): RelevantCountField | null {
  return isQuantityBenchmark(benchmarkType) ? relevantCountField ?? null : null;
}

/**
 * The unit shown in the row's main Count input, or null when the row has none
 * (a lumpsum where nothing is picked yet, or an activity with no benchmark at
 * all — both keep all six units in "Other counts", exactly as today).
 */
export function primaryCountField({
  benchmarkType,
  relevantCountField,
  selectedCountField,
}: {
  benchmarkType: BenchmarkType | null | undefined;
  relevantCountField: RelevantCountField | null | undefined;
  /** The employee's pick from the Count dropdown (lumpsum rows only). */
  selectedCountField?: string | null;
}): RelevantCountField | null {
  const configured = benchmarkCountField(benchmarkType, relevantCountField);
  if (configured) return configured;
  if (!isLumpsumUnitRow(benchmarkType, relevantCountField)) return null;
  return asCountField(selectedCountField);
}

/**
 * The units left for "Other counts" — every unit except the one already shown
 * in the Count row. This is what prevents a second, duplicate input for the
 * selected field; it applies to all six units identically.
 */
export function otherCountFields(
  primary: RelevantCountField | null,
): CountFieldName[] {
  const primaryName = primary ? countFieldName(primary) : null;
  return ALL_COUNT_FIELDS.filter((name) => name !== primaryName);
}

/**
 * Where the Count input holds its value while NO field has been named yet.
 *
 * A named count lives in that unit's own column (tags_count, …) — there is
 * nowhere else for it to go, and that is what makes the export work without a
 * mapping. But the employee may type the number BEFORE naming the field, so the
 * form needs somewhere to keep it in the meantime. That is this slot: it holds
 * an unattributed count, and naming a field immediately moves the number out of
 * it and into that unit's column.
 *
 * It is sent to the server too, so the server can REJECT an unattributed count
 * rather than having to guess which column it meant (see the backend's
 * `count_value`). A well-formed payload therefore carries it only in the state
 * the server refuses.
 */
export const LUMPSUM_STAGED_COUNT = "count_value" as const;

/** The form field the Count input binds to: the named unit's own column, or the
 *  staging slot while nothing is named. */
export const lumpsumCountName = (
  primary: RelevantCountField | null,
): CountFieldName | typeof LUMPSUM_STAGED_COUNT =>
  primary ? countFieldName(primary) : LUMPSUM_STAGED_COUNT;

/**
 * Whether a count input holds a number worth attributing.
 *
 * Empty and 0 both mean "nothing counted", matching the count columns
 * themselves: they are NOT NULL DEFAULT 0, so an untouched unit already reads 0.
 * Treating a typed 0 as a value would force a field to be picked for it and
 * then immediately have that field cleared again as empty.
 */
export const hasCountValue = (value: string | null | undefined): boolean =>
  typeof value === "string" && value.trim() !== "" && Number(value) > 0;

/**
 * The conditional requirement, in one place for the form schema, the editor and
 * (mirrored) the backend:
 *
 *   a count was entered  -> the field it belongs to is REQUIRED
 *   no count was entered -> the field is optional, and the activity saves
 *
 * An activity with nothing to count is a normal, valid activity — this never
 * makes the Count itself mandatory.
 */
export const countNeedsField = (
  countValue: string | null | undefined,
  countField: string | null | undefined,
): boolean => hasCountValue(countValue) && !asCountField(countField);

/** The message shown against the field picker when a count has no field. */
export const COUNT_FIELD_REQUIRED_MESSAGE =
  "Please select a field for the entered count.";
