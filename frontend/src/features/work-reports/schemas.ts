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
] as const;

export const WORK_REPORT_STATUS_LABEL: Record<WorkReportStatus, string> = {
  draft: "Draft",
  submitted: "Submitted",
  approved: "Approved",
  rejected: "Rejected",
};

// ── day status ────────────────────────────────────────────────────────────────

export const DAY_STATUSES = [
  "on_duty",
  "half_day",
  "on_leave",
  "wfh",
  "permission",
  "comp_off",
] as const;

export type DayStatus = (typeof DAY_STATUSES)[number];

export const DAY_STATUS_LABEL: Record<DayStatus, string> = {
  on_duty: "On Duty",
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

// ── task schema ───────────────────────────────────────────────────────────────

// minutes_spent is kept as a string in form inputs so an empty value maps to null.
const minutesSpentSchema = z
  .string()
  .refine(
    (v) => {
      if (v.trim() === "") return true; // null/omitted — OK
      const n = Number(v);
      return Number.isInteger(n) && n >= 0 && n <= MAX_DAY_MINUTES;
    },
    `Enter whole minutes between 0 and ${MAX_DAY_MINUTES}, or leave blank`,
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
  description: z
    .string()
    .min(1, "Description is required")
    .max(DESCRIPTION_MAX, `Keep under ${DESCRIPTION_MAX} characters`),
  minutes_spent: minutesSpentSchema,
  activity_type: z.string().max(200).optional().default(""),
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
    const total = v.tasks.reduce((sum, t) => sum + (Number(t.minutes_spent) || 0), 0);
    if (total > MAX_DAY_MINUTES) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `Total minutes (${total}) exceed a single day (${MAX_DAY_MINUTES})`,
        path: ["tasks"],
      });
    }
  });

export type WorkReportFormValues = z.infer<typeof workReportFormSchema>;

// ── empty defaults ────────────────────────────────────────────────────────────

export const EMPTY_TASK_ROW: WorkReportFormValues["tasks"][number] = {
  project_id:   "",
  description:  "",
  minutes_spent: "",
  activity_type: "",
  tags_count:   "0",
  docs_count:   "0",
  bom_count:    "0",
  spares_count: "0",
};

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

// ── review note ───────────────────────────────────────────────────────────────

export const reviewNoteSchema = z.object({
  review_note: z
    .string()
    .min(1, "A reason is required")
    .max(REVIEW_NOTE_MAX, `Keep under ${REVIEW_NOTE_MAX} characters`),
});

export type ReviewNoteValues = z.infer<typeof reviewNoteSchema>;

// ── API body converters ───────────────────────────────────────────────────────

const orNull = (v: string | undefined): string | null =>
  !v || v.trim() === "" ? null : v;

const toCount = (v: string | undefined): number =>
  Number.isFinite(Number(v)) ? Math.max(0, Math.trunc(Number(v))) : 0;

const toMinutes = (v: string | undefined): number | null => {
  if (!v || v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? Math.trunc(n) : null;
};

function toTasks(v: WorkReportFormValues) {
  return v.tasks.map((t) => ({
    project_id:    t.project_id,
    description:   t.description.trim(),
    minutes_spent: toMinutes(t.minutes_spent),
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
            project_id:    t.project_id,
            description:   t.description,
            minutes_spent: t.minutes_spent != null ? String(t.minutes_spent) : "",
            activity_type: t.activity_type ?? "",
            tags_count:    String(t.tags_count ?? 0),
            docs_count:    String(t.docs_count ?? 0),
            bom_count:     String(t.bom_count ?? 0),
            spares_count:  String(t.spares_count ?? 0),
          }))
        : [{ ...EMPTY_TASK_ROW }],
  };
}
