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
  "on_duty",
  "office",
  "half_day",
  "on_leave",
  "wfh",
  "permission",
  "comp_off",
] as const;

export type DayStatus = (typeof DAY_STATUSES)[number];

export const DAY_STATUS_LABEL: Record<DayStatus, string> = {
  on_duty: "On Duty",
  office: "Office",
  half_day: "Half Day",
  on_leave: "On Leave",
  wfh: "Work From Home",
  permission: "Permission",
  comp_off: "Comp Off",
};

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

// ── duration conversion (UI shows hours; backend stores whole minutes) ─────────

/** Form hours string → whole minutes for the API. Empty ⇒ null. */
export const hoursToMinutes = (v: string | undefined): number | null => {
  if (!v || v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? Math.round(n * 60) : null;
};

/** API minutes → clean hours string for the form (60→"1", 90→"1.5", 135→"2.25"). */
export const minutesToHours = (m: number): string => String(+(m / 60).toFixed(2));

// ── task schema ───────────────────────────────────────────────────────────────

// duration_hours is kept as a string in form inputs so an empty value maps to null.
// Decimal hours allowed (e.g. 1, 1.5, 2.25, 7.75); 24h == the 1440-minute day cap.
const durationHoursSchema = z
  .string()
  .refine(
    (v) => {
      if (v.trim() === "") return true; // null/omitted — OK (duration is optional)
      const n = Number(v);
      return Number.isFinite(n) && n >= 0 && n <= MAX_DAY_HOURS;
    },
    `Enter hours between 0 and ${MAX_DAY_HOURS} (decimals allowed), or leave blank`,
  );

// Count inputs: string → non-negative int, empty = 0
const countSchema = z
  .string()
  .refine(
    (v) => v.trim() === "" || (Number.isInteger(Number(v)) && Number(v) >= 0),
    "Enter a whole number ≥ 0",
  );

const taskSchema = z.object({
  project_id: z.string().min(1, "Project is required"),
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
  duration_hours: durationHoursSchema,
  activity_type: z.string().min(1, "Activity type is required").max(200),
  tags_count:   countSchema.default("0"),
  docs_count:   countSchema.default("0"),
  bom_count:    countSchema.default("0"),
  spares_count: countSchema.default("0"),
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
    tasks: z.array(taskSchema).min(1, "Add at least one task"),
  })
  .superRefine((v, ctx) => {
    // Required: Day Status + Office Location (enforced here so the inferred
    // form type keeps these optional/undefined-friendly).
    if (v.day_status === undefined) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Day Status is required",
        path: ["day_status"],
      });
    }
    if (v.location === undefined) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Office Location is required",
        path: ["location"],
      });
    }
    const totalMin = v.tasks.reduce((sum, t) => sum + (hoursToMinutes(t.duration_hours) || 0), 0);
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
  project_name:   undefined,
  project_code:   undefined,
  description:    "",
  duration_hours: "",
  activity_type:  "",
  tags_count:     "0",
  docs_count:     "0",
  bom_count:      "0",
  spares_count:   "0",
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
    description:   t.description.trim(),
    minutes_spent: hoursToMinutes(t.duration_hours),
    activity_type: orNull(t.activity_type),
    tags_count:    toCount(t.tags_count),
    docs_count:    toCount(t.docs_count),
    bom_count:     toCount(t.bom_count),
    spares_count:  toCount(t.spares_count),
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
            project_name:   t.project_name ?? undefined,
            project_code:   t.project_code ?? undefined,
            description:    t.description,
            duration_hours: t.minutes_spent != null ? minutesToHours(t.minutes_spent) : "",
            activity_type:  t.activity_type ?? "",
            tags_count:    String(t.tags_count ?? 0),
            docs_count:    String(t.docs_count ?? 0),
            bom_count:     String(t.bom_count ?? 0),
            spares_count:  String(t.spares_count ?? 0),
          }))
        : [{ ...EMPTY_TASK_ROW }],
  };
}
