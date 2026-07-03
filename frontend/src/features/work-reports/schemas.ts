import { z } from "zod";

import type {
  WorkReport,
  WorkReportCreateBody,
  WorkReportStatus,
  WorkReportUpdateBody,
} from "./types";

// ── status ──────────────────────────────────────────────────────────────────

export const WORK_REPORT_STATUSES = [
  "draft",
  "submitted",
  "approved",
  "rejected",
  "granted",
] as const;

export const WORK_REPORT_STATUS_LABEL: Record<WorkReportStatus, string> = {
  draft: "Draft",
  submitted: "Submitted",
  approved: "Approved",
  rejected: "Rejected",
  granted: "Granted",
};

// ── day status ────────────────────────────────────────────────────────────────

export const DAY_STATUSES = [
  "leave",
  "company_holiday",
  "work_from_home",
  "week_off",
  "work_at_office",
  "half_day",
  "comp_off",
  "overtime_compensation",
  "overtime_salary",
  "permission_first_half_1hr",
  "permission_second_half_1hr",
  "permission_first_half_2hr",
  "permission_second_half_2hr",
] as const;

export type DayStatus = (typeof DAY_STATUSES)[number];

export const DAY_STATUS_LABEL: Record<DayStatus, string> = {
  leave: "Leave",
  company_holiday: "Company Holiday",
  work_from_home: "Work From Home",
  week_off: "Week Off",
  work_at_office: "Work at Office",
  half_day: "Half Day",
  comp_off: "Comp-off",
  overtime_compensation: "Overtime Hours-Compensation",
  overtime_salary: "Overtime Hours-Salary",
  // "P / …" marks a Present day on which the employee took some permission.
  permission_first_half_1hr: "P / Permission-First Half 1HR",
  permission_second_half_1hr: "P / Permission-Second Half 1HR",
  permission_first_half_2hr: "P / Permission-First Half 2HR",
  permission_second_half_2hr: "P / Permission-Second Half 2HR",
};

// Day statuses where the employee did no project work: the report needs no
// activities and is exempt from benchmark / overdue / pending tracking. Only
// Remarks and Query stay active on the form for these.
export const NO_ACTIVITY_DAY_STATUSES = new Set<DayStatus>([
  "week_off",
  "leave",
  "company_holiday",
  "comp_off",
]);

export const isNoActivityDayStatus = (s: DayStatus | undefined): boolean =>
  s !== undefined && NO_ACTIVITY_DAY_STATUSES.has(s);

// ── location ──────────────────────────────────────────────────────────────────

export const WORK_LOCATIONS = ["hyderabad", "chennai", "qatar"] as const;

export type WorkLocation = (typeof WORK_LOCATIONS)[number];

export const WORK_LOCATION_LABEL: Record<WorkLocation, string> = {
  hyderabad: "Hyderabad",
  chennai: "Chennai",
  qatar: "Qatar",
};

// ── validation constants ──────────────────────────────────────────────────────

const DESCRIPTION_MAX = 2000;
const REMARKS_MAX     = 2000;
const REVIEW_NOTE_MAX = 1000;
const MAX_DAY_MINUTES = 1440;
const MAX_DAY_HOURS   = 24;

// ── duration conversion (UI uses H.MM clock notation; backend stores minutes) ──
// "2.20" means 2 hours 20 minutes (= 140 min), NOT 2.2 decimal hours.

/** Form time string "H" or "H.MM" → whole minutes. "2.20" → 140. Empty/invalid ⇒ null. */
export const hoursToMinutes = (v: string | undefined): number | null => {
  if (!v || v.trim() === "") return null;
  const match = /^(\d+)(?:[.:](\d{1,2}))?$/.exec(v.trim());
  if (!match) return null;
  const h = parseInt(match[1], 10);
  const m = match[2] != null ? parseInt(match[2], 10) : 0;
  if (m > 59) return null; // minutes must be 00–59
  return h * 60 + m;
};

/** Whole minutes → "H.MM" string for the form (60→"1", 140→"2.20", 125→"2.05"). */
export const minutesToHours = (mins: number): string => {
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m === 0 ? String(h) : `${h}.${String(m).padStart(2, "0")}`;
};

// ── task schema ───────────────────────────────────────────────────────────────

// Time is entered in H.MM clock notation (e.g. "2.20" = 2h20m). Kept as a string
// so an empty value maps to null; 24h == the 1440-minute day cap.
const durationHoursSchema = z
  .string()
  .refine(
    (v) => {
      if (v.trim() === "") return true; // null/omitted — OK (duration is optional)
      const mins = hoursToMinutes(v);
      return mins !== null && mins <= MAX_DAY_MINUTES;
    },
    "Enter time as HH.MM (e.g. 2.30) — minutes 00–59, max 24h",
  );

// Count inputs: string → non-negative int, empty = 0
const countSchema = z
  .string()
  .refine(
    (v) => v.trim() === "" || (Number.isInteger(Number(v)) && Number(v) >= 0),
    "Enter a whole number ≥ 0",
  );

const taskSchema = z
  .object({
    project_id: z.string().min(1, "Project is required"),
    // Optional link to an assigned task; selecting one fills in the project.
    task_id: z.string().optional().default(""),
    task_title: z.string().optional(),
    // Task-based hours (separate from the project-activity duration below).
    task_hours: durationHoursSchema,
    // Display-only snapshot fields — populated from API in edit mode so the
    // Combobox can show the project name/code even when the project is no
    // longer in the RBAC-scoped list.  Never sent back to the backend.
    project_name: z.string().optional(),
    project_code: z.string().optional(),
    // Day remarks — optional free text describing the activity.
    description: z
      .string()
      .max(DESCRIPTION_MAX, `Keep under ${DESCRIPTION_MAX} characters`)
      .optional()
      .default(""),
    // Project-activity hours. The input was retired from the day-based form;
    // the column is kept (sent as null) so existing data round-trips and the
    // field can be reinstated without a migration.
    duration_hours: durationHoursSchema,
    // Legacy free-text activity label. Kept for backward round-tripping of
    // rows saved before the Activity Master existed; new rows are selected
    // via activity_id/sub_activity_id below and the server derives this.
    activity_type: z.string().max(200).optional().default(""),
    // Activity Master selection. activity_id is a UI-only filter (never sent
    // to the backend); sub_activity_id is the real selection.
    activity_id: z.string().optional().default(""),
    sub_activity_id: z.string().optional().default(""),
    sub_activity_name: z.string().optional(),
    activity_name: z.string().optional(),
    // NUMERIC sub-activities are benchmarked directly against whichever of
    // these four the chosen sub-activity's relevant_count_field names — there
    // is no separate "actual count" field, so a value is never entered twice.
    tags_count:   countSchema.default("0"),
    docs_count:   countSchema.default("0"),
    bom_count:    countSchema.default("0"),
    spares_count: countSchema.default("0"),
    // TASK_BASED sub-activities only — the completion checkbox. started_date/
    // due_date/completed_date are never user-entered; they're system-managed
    // (shown read-only from the API, set via the dedicated completion-toggle
    // endpoint — see useToggleTaskCompletion).
    is_completed: z.boolean().default(false),
    started_date: z.string().optional(),
    due_date: z.string().optional(),
    completed_date: z.string().optional(),
    // Maintenance Plant the employee worked at — independent of the
    // project's own assigned plant. Optional: pick it directly; Planning Plant
    // code/description auto-derive (display-only, never sent to the backend).
    maintenance_plant_id: z.string().optional().default(""),
    maintenance_plant_code: z.string().optional(),
    maintenance_plant_description: z.string().optional(),
    planning_plant_code: z.string().optional(),
    planning_plant_description: z.string().optional(),
  })
  .superRefine((v, ctx) => {
    // Legacy rows (pre-Activity Master) keep their free-text activity_type and
    // are exempt — new rows must pick both an Activity and a Sub-Activity.
    if (!v.activity_type.trim() && !v.sub_activity_id.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Activity is required",
        path: ["activity_id"],
      });
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Select a Sub-Activity",
        path: ["sub_activity_id"],
      });
    }
  });

// ── report form schema ────────────────────────────────────────────────────────

export const workReportFormSchema = z
  .object({
    report_date: z.string().min(1, "Date is required"),
    day_status: z.enum(DAY_STATUSES).optional(),
    location:   z.enum(WORK_LOCATIONS).optional(),
    well_head_no: z.string().max(500).optional().default(""),
    pm_plant:     z.string().max(500).optional().default(""),
    task_list_count:        countSchema.default("0"),
    task_list_op_count:     countSchema.default("0"),
    maintenance_item_count: countSchema.default("0"),
    maintenance_plan_count: countSchema.default("0"),
    remarks:    z.string().max(REMARKS_MAX, `Keep under ${REMARKS_MAX} characters`).default(""),
    query_text: z.string().max(REMARKS_MAX, `Keep under ${REMARKS_MAX} characters`).default(""),
    // Empty for leave-type day statuses (the form clears + freezes the activity
    // editor); a working-day status requires ≥1 activity — enforced below.
    tasks: z.array(taskSchema),
  })
  .superRefine((v, ctx) => {
    // Leave-type days (week off / leave / company holiday / comp-off): the
    // employee did no project work, so Office Location and activities are not
    // required — only Day Status, Remarks and Query apply.
    const noActivity = isNoActivityDayStatus(v.day_status);

    // Required: Day Status (always). Office Location only on working days.
    if (v.day_status === undefined) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Day Status is required",
        path: ["day_status"],
      });
    }
    if (!noActivity && v.location === undefined) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Office Location is required",
        path: ["location"],
      });
    }
    if (!noActivity && v.tasks.length === 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Add at least one activity",
        path: ["tasks"],
      });
    }
    const totalMin = v.tasks.reduce(
      (sum, t) =>
        sum + (hoursToMinutes(t.duration_hours) || 0) + (hoursToMinutes(t.task_hours) || 0),
      0,
    );
    if (totalMin > MAX_DAY_MINUTES) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `Total hours (${+(totalMin / 60).toFixed(2)}) exceed a single day (${MAX_DAY_HOURS})`,
        path: ["tasks"],
      });
    }
  });

export type WorkReportFormValues = z.infer<typeof workReportFormSchema>;

// ── empty defaults ────────────────────────────────────────────────────────────

export const EMPTY_TASK_ROW: WorkReportFormValues["tasks"][number] = {
  project_id:     "",
  task_id:        "",
  task_title:     undefined,
  task_hours:     "",
  project_name:   undefined,
  project_code:   undefined,
  description:    "",
  duration_hours: "",
  activity_type:  "",
  activity_id:       "",
  sub_activity_id:   "",
  sub_activity_name: undefined,
  activity_name:     undefined,
  tags_count:     "0",
  docs_count:     "0",
  bom_count:      "0",
  spares_count:   "0",
  is_completed:   false,
  started_date:   undefined,
  due_date:       undefined,
  completed_date: undefined,
  maintenance_plant_id:          "",
  maintenance_plant_code:        undefined,
  maintenance_plant_description: undefined,
  planning_plant_code:           undefined,
  planning_plant_description:    undefined,
};

// ── review note (reject dialog) ─────────────────────────────────────────────

export const reviewNoteSchema = z.object({
  review_note: z
    .string()
    .min(1, "A reason is required")
    .max(REVIEW_NOTE_MAX, `Keep under ${REVIEW_NOTE_MAX} characters`),
});

export type ReviewNoteValues = z.infer<typeof reviewNoteSchema>;

export const editRequestSchema = z.object({
  note: z
    .string()
    .min(1, "Tell your reviewer why you need to edit")
    .max(REVIEW_NOTE_MAX, `Keep under ${REVIEW_NOTE_MAX} characters`),
});

export type EditRequestValues = z.infer<typeof editRequestSchema>;

export const EMPTY_WORK_REPORT_FORM: WorkReportFormValues = {
  report_date:  "",
  day_status:   undefined,
  location:     undefined,
  well_head_no: "",
  pm_plant:     "",
  task_list_count:        "0",
  task_list_op_count:     "0",
  maintenance_item_count: "0",
  maintenance_plan_count: "0",
  remarks:    "",
  query_text: "",
  tasks: [{ ...EMPTY_TASK_ROW }],
};

// ── API body converters ───────────────────────────────────────────────────────

const orNull = (v: string | undefined): string | null =>
  !v || v.trim() === "" ? null : v;

const toCount = (v: string | undefined): number =>
  Number.isFinite(Number(v)) ? Math.max(0, Math.trunc(Number(v))) : 0;

function toTasks(v: WorkReportFormValues) {
  return v.tasks.map((t) => ({
    project_id:    t.project_id,
    task_id:       orNull(t.task_id),
    description:   t.description.trim(),
    minutes_spent: hoursToMinutes(t.duration_hours),
    task_minutes_spent: hoursToMinutes(t.task_hours),
    activity_type: orNull(t.activity_type),
    sub_activity_id: orNull(t.sub_activity_id),
    tags_count:    toCount(t.tags_count),
    docs_count:    toCount(t.docs_count),
    bom_count:     toCount(t.bom_count),
    spares_count:  toCount(t.spares_count),
    is_completed:  t.is_completed,
    maintenance_plant_id: orNull(t.maintenance_plant_id),
  }));
}

export function toCreateBody(v: WorkReportFormValues): WorkReportCreateBody {
  return {
    report_date:   v.report_date,
    day_status:    v.day_status ?? null,
    location:      v.location ?? null,
    remarks:       orNull(v.remarks),
    query_text:    orNull(v.query_text),
    well_head_no:  orNull(v.well_head_no),
    pm_plant:      orNull(v.pm_plant),
    task_list_count:        toCount(v.task_list_count) || null,
    task_list_op_count:     toCount(v.task_list_op_count) || null,
    maintenance_item_count: toCount(v.maintenance_item_count) || null,
    maintenance_plan_count: toCount(v.maintenance_plan_count) || null,
    tasks: toTasks(v),
  };
}

export function toUpdateBody(v: WorkReportFormValues): WorkReportUpdateBody {
  return {
    day_status:    v.day_status ?? null,
    location:      v.location ?? null,
    remarks:       orNull(v.remarks),
    query_text:    orNull(v.query_text),
    well_head_no:  orNull(v.well_head_no),
    pm_plant:      orNull(v.pm_plant),
    task_list_count:        toCount(v.task_list_count) || null,
    task_list_op_count:     toCount(v.task_list_op_count) || null,
    maintenance_item_count: toCount(v.maintenance_item_count) || null,
    maintenance_plan_count: toCount(v.maintenance_plan_count) || null,
    tasks: toTasks(v),
  };
}

export function toFormValues(report: WorkReport): WorkReportFormValues {
  return {
    report_date:   report.report_date,
    day_status:    (report.day_status as DayStatus | undefined) ?? undefined,
    location:      (report.location as WorkLocation | undefined) ?? undefined,
    well_head_no:  report.well_head_no ?? "",
    pm_plant:      report.pm_plant ?? "",
    task_list_count:        String(report.task_list_count ?? 0),
    task_list_op_count:     String(report.task_list_op_count ?? 0),
    maintenance_item_count: String(report.maintenance_item_count ?? 0),
    maintenance_plan_count: String(report.maintenance_plan_count ?? 0),
    remarks:    report.remarks ?? "",
    query_text: report.query_text ?? "",
    tasks:
      report.tasks.length > 0
        ? report.tasks.map((t) => ({
            project_id:     t.project_id,
            task_id:        t.task_id ?? "",
            task_title:     t.task_title ?? undefined,
            task_hours:     t.task_minutes_spent != null ? minutesToHours(t.task_minutes_spent) : "",
            project_name:   t.project_name ?? undefined,
            project_code:   t.project_code ?? undefined,
            description:    t.description,
            duration_hours: t.minutes_spent != null ? minutesToHours(t.minutes_spent) : "",
            activity_type:  t.activity_type ?? "",
            // activity_id is a UI-only filter; derive it so the cascading
            // Sub-Activity select pre-filters correctly when editing a row
            // that already has a sub_activity_id (resolved client-side by
            // the form against the flat sub-activity options list).
            activity_id:       "",
            sub_activity_id:   t.sub_activity_id ?? "",
            sub_activity_name: t.sub_activity_name ?? undefined,
            activity_name:     t.activity_name ?? undefined,
            tags_count:    String(t.tags_count ?? 0),
            docs_count:    String(t.docs_count ?? 0),
            bom_count:     String(t.bom_count ?? 0),
            spares_count:  String(t.spares_count ?? 0),
            is_completed:   t.is_completed ?? false,
            started_date:   t.started_date ?? undefined,
            due_date:       t.due_date ?? undefined,
            completed_date: t.completed_date ?? undefined,
            maintenance_plant_id:          t.maintenance_plant_id ?? "",
            maintenance_plant_code:        t.maintenance_plant_code ?? undefined,
            maintenance_plant_description: t.maintenance_plant_description ?? undefined,
            planning_plant_code:           t.planning_plant_code ?? undefined,
            planning_plant_description:    t.planning_plant_description ?? undefined,
          }))
        : [{ ...EMPTY_TASK_ROW }],
  };
}
