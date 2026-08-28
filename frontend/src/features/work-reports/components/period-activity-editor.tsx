"use client";

/**
 * PeriodActivityEditor — the reusable per-activity-row editor extracted from
 * the classic work-report form (see work-report-form.tsx), so Full Day, First
 * Half and Second Half all render the exact same rows instead of duplicating
 * the logic. The rows live in ONE flat `tasks` field array on the form; the
 * editor receives the `indices` belonging to its period and a `fraction`
 * (1 for a full day, 0.5 for a half / legacy half-day) that scales every
 * displayed benchmark target the way the backend will freeze it at submit.
 */
import * as React from "react";
import { type UseFormReturn } from "react-hook-form";
import { Check, Trash2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Combobox } from "@/components/ui/combobox";
import { CountInput } from "@/components/ui/count-input";
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  COUNT_FIELD_KEY,
  COUNT_FIELD_LABEL,
  isQuantityBenchmark,
  isTaskBenchmark,
  type RelevantCountField,
  type SubActivityFlat,
} from "@/features/activity-master/types";
import { ContinuationRowStatus } from "@/features/continuation-requests/components/continuation-row-status";
import { useMaintenancePlantOptions } from "@/features/plant-master/hooks";
import { formatInt } from "@/lib/format";

import type { OpenTask } from "../types";
import {
  BENCHMARK_EXCEPTION_NO_FURTHER_AVAILABLE_WORK,
  EXCEPTION_CHECKBOX_HELP,
  EXCEPTION_CHECKBOX_LABEL,
  EXCEPTION_CONFIRMATION,
  canShowNoFurtherWorkException,
  resolveExceptionCode,
} from "../benchmark-exception";
import { scaledTarget } from "../benchmark-target";
import {
  continuationRowStatus,
  openTaskInlineSummary,
} from "../open-task-state";
import {
  COUNT_FIELD_OPTIONS,
  LUMPSUM_STAGED_COUNT,
  asCountField,
  countFieldName,
  hasCountValue,
  isLumpsumUnitRow,
  lumpsumCountName,
  otherCountFields,
  primaryCountField,
  type CountFieldName,
} from "../ls-count";
import { type WorkReportFormValues } from "../schemas";

// COUNT_FIELD_KEY / COUNT_FIELD_LABEL are imported from activity-master/types:
// one declaration of the six units, mirroring the backend's COUNT_FIELD_BY_UNIT.
// Which unit owns the main Count input, and which are left to "Other counts",
// is decided by ../ls-count (pure, unit-tested) — never inline here.

// Re-exported: the classic form imports both from this module.
export { countFieldName };
export type { CountFieldName };

// Human labels + badge tone for a work item's derived lifecycle.
export const LIFECYCLE_LABEL: Record<string, string> = {
  IN_PROGRESS: "In progress",
  DUE_TODAY: "Due today",
  OVERDUE: "Overdue",
  COMPLETED_ON_TIME: "Completed",
  COMPLETED_LATE: "Completed late",
};
export const LIFECYCLE_VARIANT: Record<string, "neutral" | "warning" | "danger" | "success"> = {
  IN_PROGRESS: "neutral",
  DUE_TODAY: "warning",
  OVERDUE: "danger",
  COMPLETED_ON_TIME: "success",
  COMPLETED_LATE: "warning",
};

/** "2026-06-16" + 2 -> "2026-06-18". Client-side preview only, for a
 * TASK_BASED row that hasn't been saved yet — the server is authoritative
 * once the row exists (it computes due_date the same way, on save). */
function addDays(isoDate: string, days: number): string | null {
  const d = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(d.getTime())) return null;
  d.setDate(d.getDate() + days);
  // Format from local parts (not toISOString, which would shift the day by the
  // UTC offset and land a day early in IST).
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

const MONTH_ABBR = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** "2026-07-18" -> "18 Jul 2026". Parsed from the string's own parts rather
 *  than via Date, which would shift the day by the UTC offset in IST. */
function formatDueDate(isoDate: string | null | undefined): string | null {
  if (!isoDate) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!m) return null;
  const month = MONTH_ABBR[Number(m[2]) - 1];
  if (!month) return null;
  return `${Number(m[3])} ${month} ${m[1]}`;
}

/** Words that carry no instruction of their own — they only glue a period or a
 *  target together ("COMPLETE IN 1 DAY", "500 REQUIRED PAGES/DAY"). */
const FILLER_REMARK_WORDS = new Set([
  "COMPLETE", "COMPLETED", "COMPLETION", "FINISH", "WITHIN", "IN", "PER", "A",
  "AN", "OF", "TARGET", "REQUIRED", "REQUIREMENT", "MINIMUM", "MIN", "DAY",
  "DAYS", "DAILY", "EVERY", "AND", "THE", "IS", "TO", "BE",
]);

/**
 * True when benchmark_remarks says nothing the structured fields do not already
 * say - "1DAY" beside a 1-day period, or "500 REQUIRED PAGES/DAY" beside a
 * target of 500 PAGES. Such remarks are dropped rather than repeated under a
 * "Note:" line.
 *
 * Case and whitespace are normalised for the COMPARISON ONLY; the stored
 * Activity Master value is never touched, and a remark with any leftover
 * meaningful word is always shown verbatim.
 */
function isDuplicateRemark(
  remarks: string,
  periodDays: number | null | undefined,
  benchmarkValue: number | null | undefined,
  unit: RelevantCountField | null | undefined,
): boolean {
  const tokens = remarks
    .toUpperCase()
    // "1DAY" carries no separator, so split digit/letter runs apart first.
    .replace(/(\d)([A-Z])/g, "$1 $2")
    .replace(/([A-Z])(\d)/g, "$1 $2")
    .split(/[^A-Z0-9.]+/)
    .filter(Boolean);
  if (!tokens.length) return true;

  const unitWords = unit
    ? new Set([
        COUNT_FIELD_LABEL[unit].toUpperCase(),
        // "PAGES" configured, "PAGE" written (or the reverse).
        COUNT_FIELD_LABEL[unit].toUpperCase().replace(/S$/, ""),
        `${COUNT_FIELD_LABEL[unit].toUpperCase()}S`,
      ])
    : new Set<string>();

  return tokens.every((raw) => {
    const token = raw.replace(/\.$/, "");
    if (!token) return true;
    if (FILLER_REMARK_WORDS.has(token)) return true;
    if (unitWords.has(token)) return true;
    const num = Number(token);
    if (!Number.isNaN(num)) {
      return num === periodDays || num === benchmarkValue;
    }
    return false;
  });
}

type FormControlT = UseFormReturn<WorkReportFormValues>["control"];

/**
 * Maintenance Plant picker for one task row. The options are scoped to the
 * selected project's Planning Plant — the dropdown reloads (a fresh,
 * planning-plant-filtered fetch) whenever that code changes, so a user never
 * sees Maintenance Plants from other Planning Plants. Planning Plant +
 * Description (PP) are determined by the project and shown read-only.
 */
function MaintenancePlantField({
  control,
  index,
  planningPlantCode,
  planningPlantDescription,
}: {
  control: FormControlT;
  index: number;
  planningPlantCode?: string;
  planningPlantDescription?: string;
}) {
  const hasPlanningPlant = !!planningPlantCode;
  const { options, isLoading } = useMaintenancePlantOptions(
    true,
    planningPlantCode,
    hasPlanningPlant,
  );

  return (
    <>
      <FormField
        control={control}
        name={`tasks.${index}.maintenance_plant_id`}
        render={({ field: f }) => (
          <FormItem className="min-w-0">
            <FormLabel className="block text-xs font-medium leading-none text-muted-foreground">
              Maintenance Plant
            </FormLabel>
            <FormControl>
              <Combobox
                value={f.value || ""}
                onValueChange={f.onChange}
                options={options}
                placeholder={
                  hasPlanningPlant
                    ? isLoading
                      ? "Loading plants…"
                      : "Select plant…"
                    : "Select a project first"
                }
                searchPlaceholder="Search maintenance plants…"
                emptyMessage="No plants for this Planning Plant."
                disabled={!hasPlanningPlant}
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <div className="space-y-2">
        <span className="block text-xs font-medium leading-none text-muted-foreground">
          Planning Plant
        </span>
        <div className="flex h-9 items-center rounded-md border border-input bg-muted/40 px-3 font-mono text-sm text-muted-foreground">
          {planningPlantCode ?? "—"}
        </div>
      </div>
      <div className="space-y-2">
        <span className="block text-xs font-medium leading-none text-muted-foreground">
          Description (PP)
        </span>
        <div className="flex h-9 items-center truncate rounded-md border border-input bg-muted/40 px-3 text-sm text-muted-foreground">
          {planningPlantDescription ?? "—"}
        </div>
      </div>
    </>
  );
}

/**
 * The "no further tags were available" checkbox, rendered inside the Tags count
 * panel directly below the actual Tags input.
 *
 * Ticking it does NOT change the count above it. The employee's real number is
 * what gets saved and what the benchmark report displays; the box only records
 * WHY it fell short, so the row can be evaluated as target achieved.
 *
 * Its own component for one reason: the reconciliation effect. Every
 * "clears automatically" rule — actual reached the target, actual emptied or
 * made invalid, the benchmark changed, the row stopped being a numeric TAGS row
 * — is the same rule (canShowNoFurtherWorkException stopped holding), so it is
 * enforced in ONE effect instead of a handler per input. Changing the Activity
 * or Sub-Activity clears it at the selection handler too, since that can unmount
 * this component before the effect could run.
 *
 * Renders nothing at all when the conditions are not met, so a task-based
 * activity, or a Docs / BOM / Spares / Pages / Records one, never shows it.
 */
function BenchmarkExceptionField({
  form,
  index,
  benchmarkType,
  countField,
  target,
  actual,
}: {
  form: UseFormReturn<WorkReportFormValues>;
  index: number;
  benchmarkType: SubActivityFlat["benchmark_type"];
  countField: RelevantCountField | null;
  target: number | null;
  actual: string | undefined;
}) {
  const rules = { benchmarkType, countField, target, actual };
  const visible = canShowNoFurtherWorkException(rules);
  const value = form.watch(`tasks.${index}.benchmark_exception_code`);
  // What the row SHOULD hold given what is currently selected and entered.
  const resolved = resolveExceptionCode(rules, value) ?? "";

  React.useEffect(() => {
    if (resolved !== (value ?? "")) {
      form.setValue(`tasks.${index}.benchmark_exception_code`, resolved, {
        shouldDirty: true,
      });
    }
  }, [resolved, value, form, index]);

  if (!visible) return null;

  return (
    <FormField
      control={form.control}
      name={`tasks.${index}.benchmark_exception_code`}
      render={({ field: f }) => (
        // space-y-0: the three parts space themselves, so the checkbox line and
        // its helper read as one block. sm:mt-6 drops the column past the
        // input's own label so the checkbox sits level with the input beside it.
        <FormItem className="space-y-0 sm:mt-6">
          {/* The checkbox stays OUTSIDE the numeric input — inside it, it would
              read as part of the value control. */}
          <label className="flex cursor-pointer items-start gap-2">
            <FormControl>
              <Checkbox
                className="mt-0.5 shrink-0"
                checked={f.value === BENCHMARK_EXCEPTION_NO_FURTHER_AVAILABLE_WORK}
                onChange={(e) =>
                  f.onChange(
                    e.target.checked
                      ? BENCHMARK_EXCEPTION_NO_FURTHER_AVAILABLE_WORK
                      : "",
                  )
                }
              />
            </FormControl>
            {/* The most prominent text in this column. */}
            <span className="text-sm font-medium leading-snug text-foreground">
              {EXCEPTION_CHECKBOX_LABEL}
            </span>
          </label>
          {/* Smaller and muted, indented to the label's text edge. */}
          <p className="mt-1 pl-6 text-xs leading-snug text-muted-foreground">
            {EXCEPTION_CHECKBOX_HELP}
          </p>
          {f.value === BENCHMARK_EXCEPTION_NO_FURTHER_AVAILABLE_WORK && (
            // Compact success message, directly under the checkbox it belongs
            // to rather than spanning the activity card. Uses the design
            // system's success token (green-600) at the same
            // tint/border/text weights as Badge variant="success".
            <p
              className="mt-2 ml-6 flex items-start gap-1.5 rounded-md border border-success/20 bg-success/10 px-2 py-1.5 text-xs font-medium leading-snug text-success"
              role="status"
            >
              <Check className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
              <span>{EXCEPTION_CONFIRMATION}</span>
            </p>
          )}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

/** Everything the row renderer needs from the parent form — bundled once so
 *  Full Day and the two half cards pass identical context. */
export interface ActivityEditorContext {
  form: UseFormReturn<WorkReportFormValues>;
  /** Field-array entries (for stable row keys). */
  fields: { id: string }[];
  watchedTasks: WorkReportFormValues["tasks"] | undefined;
  reportDate: string;
  projectOptions: React.ComponentProps<typeof Combobox>["options"];
  projById: Map<
    string,
    {
      code?: string | null;
      job_code_code?: string | null;
      planning_plant_code?: string | null;
      planning_plant_description?: string | null;
    }
  >;
  activityOptions: { value: string; label: string }[];
  subActivityById: Map<string, SubActivityFlat>;
  subActivityOptionsByActivity: Map<string, { value: string; label: string }[]>;
  continuationEnabled: boolean;
  openBySubProject: Map<string, OpenTask>;
  startNewRows: Set<number>;
  setStartNewRows: React.Dispatch<React.SetStateAction<Set<number>>>;
  attachToRow: (index: number, t: OpenTask) => void;
  clearRowPlant: (index: number) => void;
  /** Remove a row (parent owns field-array + draft bookkeeping). */
  removeRow: (index: number) => void;
  /** Whether the row's delete control is active. */
  canRemove: (index: number) => boolean;
}

export function PeriodActivityEditor({
  ctx,
  indices,
  fraction,
  hideRemoveControls = false,
}: {
  ctx: ActivityEditorContext;
  indices: number[];
  /** Benchmark scaling for this period: 1 full day, 0.5 half day. Applied to
   *  every displayed target exactly as the backend freezes it at submit. */
  fraction: number;
  /** Split Day: the half's single activity is mandatory while it is working,
   *  so the row carries no delete control — the only way to remove it is to
   *  switch the half to a leave/off status and confirm. Full Day is unaffected
   *  and keeps its per-row delete. */
  hideRemoveControls?: boolean;
}) {
  const {
    form, fields, watchedTasks, reportDate, projectOptions, projById,
    activityOptions, subActivityById, subActivityOptionsByActivity,
    continuationEnabled, openBySubProject, startNewRows, setStartNewRows,
    attachToRow, clearRowPlant, removeRow, canRemove,
  } = ctx;

  return (
    <>
      {indices.map((index) => {
        const selectedProjectId = watchedTasks?.[index]?.project_id;
        const selectedProject = selectedProjectId
          ? projById.get(selectedProjectId)
          : undefined;
        // Prefer the live RBAC-scoped project; fall back to the task snapshot
        // (edit mode where the project is archived / no longer accessible).
        const projectCodeLabel =
          selectedProject?.code ?? watchedTasks?.[index]?.project_code ?? "—";
        const jobCodeLabel = selectedProject?.job_code_code ?? "—";

        // Task continuation, per row.
        const rowSubId = watchedTasks?.[index]?.sub_activity_id;
        const rowWorkItemId = watchedTasks?.[index]?.work_item_id;
        const rowLifecycle = watchedTasks?.[index]?.work_item_lifecycle;
        const rowStarted = watchedTasks?.[index]?.started_date;
        const isContinuation = continuationEnabled && !!rowWorkItemId;
        // A manual sub-activity pick that matches an open work item ->
        // offer an explicit Continue existing / Start a new task choice
        // (unless already linked or the user chose Start-new for this row).
        const rowOpenItem =
          continuationEnabled && selectedProjectId && rowSubId
            ? openBySubProject.get(`${selectedProjectId}|${rowSubId}`)
            : undefined;
        const rowOpenMatch = !rowWorkItemId ? rowOpenItem : undefined;
        // One derivation of this row's continuation state, from the saved status
        // when there is one and from the open item it continues when there is
        // not (a row just attached in this editor has nothing saved yet). It is
        // purely a label - it gates nothing. A pending continuation does not
        // disable the completion checkbox and never blocked saving or
        // submitting: approval decides whether that work is accepted, not what
        // the employee is allowed to fill in.
        const rowContinuationStatus = continuationRowStatus(
          (watchedTasks?.[index]?.continuation_approval_status ?? null) as
            | "pending"
            | "approved"
            | "rejected"
            | null,
          isContinuation ? rowOpenItem : undefined,
        );

        return (
          <div
            key={fields[index]?.id ?? index}
            className="space-y-5 rounded-lg border border-border p-4"
          >
            {/* Row remove control (Full Day only — see hideRemoveControls). */}
            {!hideRemoveControls && (
              <div className="flex items-end justify-end gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => removeRow(index)}
                  disabled={!canRemove(index)}
                  aria-label="Remove activity"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            )}

            {/* Continuation banner: this row continues an existing work
                item. Project/Activity/Sub are locked (the backend forbids
                changing them on a continuation). */}
            {isContinuation && (
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-sm">
                <span className="flex flex-wrap items-center gap-x-2">
                  <span>
                    Continuing task started on{" "}
                    <span className="font-medium">{rowStarted ?? "—"}</span>
                    {watchedTasks?.[index]?.due_date && (
                      <> · due {watchedTasks[index].due_date}</>
                    )}
                  </span>
                  {/* A saved continuation past the allowed duration says whether
                      it is still awaiting the Project Head, so re-opening the
                      report never presents pending work as accepted. */}
                  <ContinuationRowStatus
                    task={{ continuation_approval_status: rowContinuationStatus }}
                    compact
                  />
                </span>
                {rowLifecycle && (
                  <Badge variant={LIFECYCLE_VARIANT[rowLifecycle] ?? "neutral"}>
                    {LIFECYCLE_LABEL[rowLifecycle] ?? rowLifecycle}
                  </Badge>
                )}
              </div>
            )}

            {/* Manual pick matched an open work item: explicit choice. */}
            {rowOpenMatch && !startNewRows.has(index) && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-dashed border-border bg-muted/30 px-3 py-2 text-sm">
                <span className="text-muted-foreground">
                  You have an open task for this activity (
                  {openTaskInlineSummary(rowOpenMatch)}).
                  {rowOpenMatch.requires_continuation_approval &&
                    (rowOpenMatch.continuation_status === "rejected" ? (
                      <>
                        {" "}
                        Project Head rejected continuation of this task - it cannot
                        be continued further.
                      </>
                    ) : (
                      <>
                        {" "}
                        This task&apos;s allowed duration has passed; continuing it
                        will be sent to your Project Head for approval.
                      </>
                    ))}
                </span>
                <div className="flex items-center gap-2">
                  {/* UI-only defence in depth: the authoritative block is the
                      server-side continuation gate, which 403s the save
                      (now scoped to a rejected request specifically). */}
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={() => attachToRow(index, rowOpenMatch)}
                    disabled={rowOpenMatch.continuation_status === "rejected"}
                  >
                    Continue existing task
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      setStartNewRows((prev) => new Set(prev).add(index))
                    }
                  >
                    Start a new task
                  </Button>
                </div>
              </div>
            )}

            {/* Row A — Project Name | Project Code | Job Code.
                Project Code / Job Code are read-only, auto-filled from the
                selected project. */}
            <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-[minmax(0,1.4fr)_120px_120px]">

              {/* Project Name — searchable combobox (name + code) */}
              <FormField
                control={form.control}
                name={`tasks.${index}.project_id`}
                render={({ field: f }) => (
                  <FormItem className="min-w-0">
                    <FormLabel className="block text-xs leading-none text-muted-foreground">
                      Project Name <span className="text-destructive">*</span>
                    </FormLabel>
                    <FormControl>
                      <Combobox
                        value={f.value}
                        onValueChange={(v) => {
                          const changed = v !== f.value;
                          f.onChange(v);
                          // Maintenance Plant options depend on the project's
                          // Planning Plant — clear any prior selection so a
                          // plant from the old Planning Plant can't linger.
                          if (changed) clearRowPlant(index);
                        }}
                        options={projectOptions}
                        placeholder="Select project…"
                        searchPlaceholder="Search by name or code…"
                        emptyMessage="No matching projects."
                        allowClear={false}
                        disabled={isContinuation}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Project Code — read-only metadata, auto-filled from selection */}
              <div className="space-y-2">
                <span className="block text-xs font-medium leading-none text-muted-foreground">
                  Project Code
                </span>
                <div className="flex h-9 items-center rounded-md border border-input bg-muted/40 px-3 font-mono text-sm text-muted-foreground">
                  {projectCodeLabel}
                </div>
              </div>

              {/* Job Code — read-only metadata, auto-filled from selection */}
              <div className="space-y-2">
                <span className="block text-xs font-medium leading-none text-muted-foreground">
                  Job Code
                </span>
                <div className="flex h-9 items-center rounded-md border border-input bg-muted/40 px-3 font-mono text-sm text-muted-foreground">
                  {jobCodeLabel}
                </div>
              </div>

            </div>

            {/* Row A2: Maintenance Plant — scoped to the selected project's
                Planning Plant (see MaintenancePlantField). */}
            <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-[minmax(0,1.4fr)_120px_minmax(0,1fr)]">
              <MaintenancePlantField
                control={form.control}
                index={index}
                planningPlantCode={
                  selectedProject?.planning_plant_code
                  ?? watchedTasks?.[index]?.planning_plant_code
                  ?? undefined
                }
                planningPlantDescription={
                  selectedProject?.planning_plant_description
                  ?? watchedTasks?.[index]?.planning_plant_description
                  ?? undefined
                }
              />
            </div>

            {/* Row B: Activity (25%) | Sub-Activity (75%) — own full-width row
                so long sub-activity names show in full, uncramped. Selections
                come from the Activity Master (Settings → Activity Master),
                never hardcoded here. */}
            <div className="grid grid-cols-[1fr_3fr] gap-4">
              <FormField
                control={form.control}
                name={`tasks.${index}.activity_id`}
                render={({ field: f }) => (
                  <FormItem className="min-w-0">
                    <FormLabel className="block text-xs leading-none text-muted-foreground">
                      Activity <span className="text-destructive">*</span>
                    </FormLabel>
                    <FormControl>
                      <Combobox
                        value={f.value || ""}
                        onValueChange={(v) => {
                          f.onChange(v);
                          // A benchmark exception describes ONE activity's
                          // available work, so it never survives a change of
                          // activity — cleared here rather than left to the
                          // field's own effect, which the change may unmount.
                          form.setValue(`tasks.${index}.benchmark_exception_code`, "");
                          // Changing the Activity invalidates any previously
                          // chosen Sub-Activity from a different Activity.
                          const currentSub = form.getValues(`tasks.${index}.sub_activity_id`);
                          if (currentSub && subActivityById.get(currentSub)?.activity_id !== v) {
                            form.setValue(`tasks.${index}.sub_activity_id`, "");
                            form.setValue(`tasks.${index}.sub_activity_name`, undefined);
                            form.setValue(`tasks.${index}.activity_name`, undefined);
                            // The lumpsum Count unit belongs to the sub-activity
                            // that was just dropped, so the pick goes with it —
                            // the number stays where it was entered rather than
                            // being silently deleted. A count still waiting for
                            // a field goes too: its input is about to unmount,
                            // and an unattributed number the employee can no
                            // longer see must not sit there blocking the save.
                            form.setValue(`tasks.${index}.count_field`, "");
                            form.setValue(`tasks.${index}.count_value`, "");
                          }
                        }}
                        options={activityOptions}
                        placeholder="Select activity…"
                        searchPlaceholder="Search activities…"
                        emptyMessage="No matching activities."
                        disabled={isContinuation}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name={`tasks.${index}.sub_activity_id`}
                render={({ field: f }) => {
                  const selectedActivityId = watchedTasks?.[index]?.activity_id;
                  const options = selectedActivityId
                    ? subActivityOptionsByActivity.get(selectedActivityId) ?? []
                    : [];
                  return (
                    <FormItem className="min-w-0">
                      <FormLabel className="block text-xs leading-none text-muted-foreground">
                        Sub-Activity <span className="text-destructive">*</span>
                      </FormLabel>
                      <FormControl>
                        <Combobox
                          value={f.value || ""}
                          onValueChange={(v) => {
                            const prev = form.getValues(
                              `tasks.${index}.sub_activity_id`,
                            );
                            f.onChange(v);
                            const sub = v ? subActivityById.get(v) : undefined;
                            form.setValue(`tasks.${index}.sub_activity_name`, sub?.name);
                            form.setValue(`tasks.${index}.activity_name`, sub?.activity_name);
                            // Server derives activity_type from the new selection.
                            form.setValue(`tasks.${index}.activity_type`, "");
                            // A new sub-activity means a new benchmark (mode,
                            // unit and target), so any exception recorded
                            // against the old one no longer describes anything.
                            form.setValue(`tasks.${index}.benchmark_exception_code`, "");
                            // The Count unit was picked for the OLD sub-activity
                            // (and the new one may not even be a lumpsum), so a
                            // real change starts it unpicked, and any count
                            // still waiting for a field is dropped with it. The
                            // counts already stored under a unit are left alone
                            // — the same treatment "Other counts" values get.
                            if (prev !== v) {
                              form.setValue(`tasks.${index}.count_field`, "");
                              form.setValue(`tasks.${index}.count_value`, "");
                            }
                            // Clear the OLD sub-activity's benchmarked count
                            // when the selection actually changes (see the
                            // classic form for the full rationale).
                            if (prev && prev !== v) {
                              const prevSub = subActivityById.get(prev);
                              const prevUnit = isQuantityBenchmark(
                                prevSub?.benchmark_type,
                              )
                                ? prevSub!.relevant_count_field
                                : null;
                              const newUnit = isQuantityBenchmark(sub?.benchmark_type)
                                ? sub!.relevant_count_field
                                : null;
                              if (prevUnit && prevUnit !== newUnit) {
                                form.setValue(
                                  `tasks.${index}.${countFieldName(prevUnit)}`,
                                  "0",
                                );
                              }
                            }
                          }}
                          options={options}
                          placeholder={selectedActivityId ? "Select sub-activity…" : "Pick an Activity first"}
                          searchPlaceholder="Search sub-activities…"
                          emptyMessage="No matching sub-activities."
                          disabled={!selectedActivityId || isContinuation}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  );
                }}
              />
            </div>

            {/* Activity Master guidance for a quantity-only mode
                (NUMERIC / NUMERIC_DAILY). Task modes render their note
                inside the Task benchmark card instead, so the same
                remark is never printed twice on one row. */}
            {(() => {
              const subId = watchedTasks?.[index]?.sub_activity_id;
              const sub = subId ? subActivityById.get(subId) : undefined;
              if (!sub || isTaskBenchmark(sub.benchmark_type)) return null;
              const remarks = sub.benchmark_remarks?.trim();
              if (!remarks) return null;
              const unit = isQuantityBenchmark(sub.benchmark_type)
                ? sub.relevant_count_field
                : null;
              if (
                isDuplicateRemark(
                  remarks,
                  sub.benchmark_period_days,
                  sub.benchmark_value,
                  unit,
                )
              ) {
                return null;
              }
              return (
                // whitespace-pre-line: multi-line remarks keep their line
                // breaks and stored wording verbatim.
                <p className="whitespace-pre-line text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">Note:</span>{" "}
                  {remarks}
                </p>
              );
            })()}

            {/* Row B2: quantity counts. The sub-activity's configured unit
                is shown prominently with its read-only target; the other
                five stay collapsed so six equal inputs are never presented.
                A LUMPSUM row has no configured unit, so it gets the combined
                "Count [25] [Tags]" row instead — same idea, one input, with the
                employee naming the unit. Either way the unit on show is removed
                from "Other counts", so no field ever has two inputs. */}
            {(() => {
              const subId = watchedTasks?.[index]?.sub_activity_id;
              const sub = subId ? subActivityById.get(subId) : undefined;
              const row = watchedTasks?.[index];
              // The configured unit — the ONLY field the benchmark reads.
              const unit = isQuantityBenchmark(sub?.benchmark_type)
                ? sub!.relevant_count_field
                : null;
              const targetName = unit ? countFieldName(unit) : null;
              // LUMPSUM (LS): Activity Master configures no unit, so the row
              // carries the employee's own pick beside its Count.
              const isLumpsum = isLumpsumUnitRow(
                sub?.benchmark_type,
                sub?.relevant_count_field,
              );
              // The unit that owns the row's main Count input — the master's on
              // a benchmarked row, the employee's pick on a lumpsum, null when
              // neither applies. Decided by the pure rule in ../ls-count, which
              // also decides what is left for "Other counts", so the two can
              // never disagree and show the same field twice.
              const primary = primaryCountField({
                benchmarkType: sub?.benchmark_type,
                relevantCountField: sub?.relevant_count_field,
                selectedCountField: row?.count_field,
              });
              // Where the lumpsum Count input reads/writes right now: the named
              // unit's own field, or the staging slot while nothing is named.
              const lumpsumValueName = lumpsumCountName(primary);
              // The clear control appears only once there is something to undo.
              const canClearLumpsum =
                !!primary || hasCountValue(row?.[lumpsumValueName]);
              // The period fraction scales every displayed target exactly as
              // the backend freezes it at submit (full day x1, half x0.5),
              // rounded up to a whole unit — half of 35 tags is 18, never 17.5.
              const targetValue = scaledTarget(sub?.benchmark_value, fraction);

              // Whether the benchmark exception applies to this row, asked of
              // the same pure rule BenchmarkExceptionField uses. Only the
              // LAYOUT is decided here — the field owns its own rendering and
              // clearing — so the two can never show a two-column row with an
              // empty second column, or vice versa.
              const canShowException = canShowNoFurtherWorkException({
                benchmarkType: sub?.benchmark_type ?? null,
                countField: unit,
                target: targetValue,
                actual: targetName ? row?.[targetName] : undefined,
              });

              // Everything except the unit already on show above — this is the
              // rule that stops a selected Tags/Docs/… appearing a second time
              // as its own free-text input.
              const others = otherCountFields(primary);
              // Never hide a stored value: if any collapsed unit already
              // carries a number, the panel opens so it stays visible.
              const othersHaveValues = others.some(
                (n) => Number(row?.[n] ?? 0) > 0,
              );

              const renderCount = (
                name: CountFieldName | typeof LUMPSUM_STAGED_COUNT,
                // null renders no label of its own — used by the lumpsum Count
                // row, which carries ONE "Count" heading over both controls so
                // the input and the field picker line up as a pair.
                label: string | null,
                prominent: boolean,
              ) => (
                <FormField
                  key={name}
                  control={form.control}
                  name={`tasks.${index}.${name}`}
                  render={({ field: f }) => (
                    <FormItem className="min-w-0">
                      {label !== null && (
                        <FormLabel
                          className={
                            prominent
                              ? "block text-sm font-semibold leading-none text-foreground"
                              : "block text-xs leading-none text-muted-foreground"
                          }
                        >
                          {label}
                          {prominent && <span className="text-destructive"> *</span>}
                        </FormLabel>
                      )}
                      <FormControl>
                        {/* CountInput (text + numeric keypad), NOT a native
                            number input: scrolling toward Save must never
                            change a focused count (the 81→83→81 bug). */}
                        <CountInput
                          placeholder="0"
                          className={prominent ? "border-primary" : undefined}
                          {...f}
                          // Select the existing value (usually the default "0")
                          // on focus so the employee can type the count straight
                          // away instead of first deleting the zero.
                          onFocus={(e) => e.currentTarget.select()}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              );

              /**
               * The LUMPSUM Count row: ONE free-typed value on the left, the
               * field it belongs to on the right.
               *
               *     Count
               *     [ 25            ] [ Tags        ▼ ]
               *
               * A SAVED count always lives in its own unit's count field
               * (tags_count here), which is why the export puts 25 under TAGS
               * without any mapping of its own, and why "Other counts" drops
               * Tags while it is selected — one field, one input, never two.
               *
               * Both halves are optional: an activity with nothing to count
               * saves with the row left empty. The pairing is what is enforced
               * — a number that has been typed must say which field it is
               * (see countNeedsField, mirrored on the server).
               *
               * The input is never frozen. Before a field is named the number
               * is kept in the staging slot; naming one moves it into that
               * unit's field, and RENAMING moves it on again — 25 entered
               * against Tags is 25 against Docs the moment Docs is chosen,
               * replacing whatever Docs held, because the employee is restating
               * which field this one count belongs to.
               */
              const repointLumpsumCount = (next: RelevantCountField) => {
                const prev = asCountField(
                  form.getValues(`tasks.${index}.count_field`),
                );
                if (prev === next) return;
                // Wherever the number is now — the old unit's field, or the
                // staging slot while it had none.
                const from = lumpsumCountName(prev);
                const carried = form.getValues(`tasks.${index}.${from}`);
                form.setValue(
                  `tasks.${index}.${from}`,
                  from === LUMPSUM_STAGED_COUNT ? "" : "0",
                  { shouldDirty: true },
                );
                form.setValue(
                  `tasks.${index}.${countFieldName(next)}`,
                  carried?.trim() ? carried : "0",
                  { shouldDirty: true },
                );
                form.setValue(`tasks.${index}.count_field`, next, {
                  shouldDirty: true,
                });
              };

              /** Put the row back to its default state — no count, no field —
               *  for an employee who decided this activity has nothing to
               *  count after all. Both halves go together: the number is
               *  cleared from wherever it currently sits, and the field is
               *  unnamed, so the row saves as an ordinary countless activity
               *  and the unit returns to "Other counts". */
              const clearLumpsumCount = () => {
                form.setValue(
                  `tasks.${index}.${lumpsumValueName}`,
                  // A unit column's default is "0" (it is about to reappear
                  // under "Other counts"); the staging slot's is empty.
                  lumpsumValueName === LUMPSUM_STAGED_COUNT ? "" : "0",
                  { shouldDirty: true },
                );
                form.setValue(`tasks.${index}.count_field`, "", {
                  shouldDirty: true,
                });
                form.clearErrors(`tasks.${index}.count_field`);
              };

              return (
                <div className="space-y-3">
                  {isLumpsum && (
                    <div className="rounded-md border border-primary/40 p-3">
                      {/* One heading over the pair — the field picker is part of
                          the Count, not a second labelled field beneath it. A
                          lumpsum row now REQUIRES both halves (see
                          validateLumpsumCounts, mirrored on the server), so the
                          heading carries the same required marker as any other
                          mandatory count. */}
                      <p className="mb-2 text-sm font-medium text-foreground">
                        Count<span className="text-destructive"> *</span>
                      </p>
                      {/* Two equal columns so the value and its field read as
                          paired controls, with the clear control taking only
                          its own width so the pair stays balanced with or
                          without it. Capped so the row does not stretch the
                          width of the card. Stacks on narrow screens. */}
                      <div className="grid grid-cols-1 gap-3 sm:max-w-xl sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-start">
                        {renderCount(lumpsumValueName, null, false)}
                        <FormField
                          control={form.control}
                          name={`tasks.${index}.count_field`}
                          render={({ field: f }) => (
                            <FormItem className="min-w-0">
                              <Select
                                value={f.value || undefined}
                                onValueChange={(v) => {
                                  const next = asCountField(v);
                                  if (next) repointLumpsumCount(next);
                                }}
                              >
                                <FormControl>
                                  <SelectTrigger>
                                    <SelectValue placeholder="Select field" />
                                  </SelectTrigger>
                                </FormControl>
                                <SelectContent>
                                  {/* Straight from the application's own list of
                                      supported count fields — never a second,
                                      hand-written one. */}
                                  {COUNT_FIELD_OPTIONS.map((o) => (
                                    <SelectItem key={o.value} value={o.value}>
                                      {o.label}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                        {/* Back to the default state: no count, no field. Only
                            offered once there is something to clear, so an
                            untouched row shows just the two controls. */}
                        {canClearLumpsum && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-9 w-9 shrink-0 justify-self-start text-muted-foreground"
                            onClick={clearLumpsumCount}
                            aria-label="Clear count"
                            title="Clear count"
                          >
                            <X className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </div>
                  )}
                  {targetName && unit && (
                    <div className="rounded-md border border-primary/40 p-3">
                      <div className="mb-2 flex flex-wrap items-baseline gap-x-2">
                        <span className="text-sm font-medium text-foreground">
                          {COUNT_FIELD_LABEL[unit]}
                        </span>
                        {fraction !== 1 && (
                          <span className="text-xs text-muted-foreground">
                            (half-day target)
                          </span>
                        )}
                      </div>
                      {/* Count input and exception control side by side on
                          desktop (~35% / ~65%, 24px gutter), stacked on narrow
                          screens. `fr` units rather than percentages so the gap
                          comes out of the row, not out of the columns.
                          The row collapses back to the single narrow input
                          whenever the exception does not apply — decided by the
                          SAME pure rule the field itself uses, so the two can
                          never disagree. */}
                      <div
                        className={
                          canShowException
                            ? "grid grid-cols-1 gap-5 sm:grid-cols-[35fr_65fr] sm:gap-6"
                            : undefined
                        }
                      >
                        <div className={canShowException ? undefined : "sm:max-w-xs"}>
                          {/* The target IS the input's label: the employee
                              reads what is expected of them on the same line
                              they type into. It comes from Activity Master
                              and is never re-entered here. */}
                          {renderCount(
                            targetName,
                            `Target: ${formatInt(targetValue)} ${COUNT_FIELD_LABEL[
                              unit
                            ].toUpperCase()} / ${sub!.benchmark_period_days ?? 1}d`,
                            true,
                          )}
                        </div>
                        {/* Beside the actual input — it is about the number
                            just entered. Stays MOUNTED even when it renders
                            nothing, so its clearing effect keeps running for a
                            row whose exception has stopped applying. */}
                        <BenchmarkExceptionField
                          form={form}
                          index={index}
                          benchmarkType={sub?.benchmark_type ?? null}
                          countField={unit}
                          target={targetValue}
                          actual={row?.[targetName]}
                        />
                      </div>
                    </div>
                  )}
                  <details open={othersHaveValues} className="group">
                    <summary className="cursor-pointer list-none text-xs text-muted-foreground hover:text-foreground">
                      <span className="group-open:hidden">
                        + Other counts (optional)
                      </span>
                      <span className="hidden group-open:inline">
                        - Other counts (optional)
                      </span>
                    </summary>
                    <div className="mt-3 grid gap-4 sm:grid-cols-3">
                      {others.map((name) =>
                        renderCount(
                          name,
                          COUNT_FIELD_LABEL[
                            (Object.keys(COUNT_FIELD_KEY) as RelevantCountField[]).find(
                              (u) => COUNT_FIELD_KEY[u] === name,
                            )!
                          ],
                          false,
                        ),
                      )}
                    </div>
                  </details>
                </div>
              );
            })()}

            {/* Row C: every TASK mode (TASK_BASED / TASK_STATUS_ONLY /
                TASK_WITH_QUANTITY) — one compact benchmark + completion card.
                Deadlines are NOT scaled by the period fraction: a half period
                changes the production target, never a task's due date. */}
            {(() => {
              const subId = watchedTasks?.[index]?.sub_activity_id;
              const sub = subId ? subActivityById.get(subId) : undefined;
              if (!isTaskBenchmark(sub?.benchmark_type)) return null;

              const row = watchedTasks?.[index];
              // Prefer the server-computed due_date (existing row);
              // for a brand-new row not yet saved, preview it
              // client-side from the report date + allocated duration.
              const periodDays = Math.max(1, sub!.benchmark_period_days ?? 1);
              const previewDue = row?.due_date
                ? row.due_date
                : reportDate
                  ? addDays(reportDate, periodDays - 1)
                  : null;
              const dueLabel = formatDueDate(previewDue);

              const unit = isQuantityBenchmark(sub!.benchmark_type)
                ? sub!.relevant_count_field
                : null;
              // Same fraction + whole-unit rule as the quantity input above.
              const target = scaledTarget(sub!.benchmark_value, fraction);

              const remarks = sub!.benchmark_remarks?.trim();
              const showNote =
                remarks &&
                !isDuplicateRemark(
                  remarks,
                  sub!.benchmark_period_days,
                  sub!.benchmark_value,
                  unit,
                );

              return (
                <div className="rounded-md border border-border p-3">
                  <p className="text-xs font-medium text-foreground">
                    Task benchmark
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {unit && target != null && dueLabel ? (
                      <>Due: {dueLabel}</>
                    ) : (
                      <>
                        Complete within {periodDays}{" "}
                        {periodDays === 1 ? "day" : "days"}.
                        {dueLabel ? ` Due: ${dueLabel}` : ""}
                      </>
                    )}
                  </p>
                  {showNote && (
                    <p className="mt-1 whitespace-pre-line text-xs text-muted-foreground">
                      <span className="font-medium text-foreground">Note:</span>{" "}
                      {remarks}
                    </p>
                  )}
                  <FormField
                    control={form.control}
                    name={`tasks.${index}.is_completed`}
                    render={({ field: f }) => (
                      <FormItem className="mt-3">
                        {!f.value && (
                          <p className="mb-2 text-xs text-muted-foreground">
                            Leave unchecked if unfinished; the task will
                            continue in your next report.
                          </p>
                        )}
                        <label className="flex items-center gap-2 text-sm">
                          <FormControl>
                            <Checkbox
                              checked={f.value}
                              onChange={(e) => f.onChange(e.target.checked)}
                            />
                          </FormControl>
                          <span className="font-medium text-foreground">
                            Mark task fully completed
                          </span>
                        </label>
                        {/* An activity awaiting a continuation decision is
                            completed like any other. The row's own status line
                            above says a decision is outstanding; it is not a
                            reason to hold up the checkbox. */}
                        {f.value && (
                          <p className="mt-2 text-xs font-medium text-foreground">
                            Task completed - it will no longer carry forward.
                          </p>
                        )}
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              );
            })()}
          </div>
        );
      })}
    </>
  );
}
