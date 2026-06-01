import { z } from "zod";

import type {
  WorkReport,
  WorkReportCreateBody,
  WorkReportStatus,
  WorkReportUpdateBody,
} from "./types";

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

const SUMMARY_MAX = 2000;
const DESCRIPTION_MAX = 2000;
const REVIEW_NOTE_MAX = 1000;
const MAX_DAY_MINUTES = 1440;

// minutes_spent is a string in the form (text input) and converted to a number
// on submit — mirrors how attendance keeps raw inputs as strings.
const taskSchema = z.object({
  project_id: z.string().min(1, "Project is required"),
  description: z
    .string()
    .min(1, "Description is required")
    .max(DESCRIPTION_MAX, `Keep under ${DESCRIPTION_MAX} characters`),
  minutes_spent: z
    .string()
    .min(1, "Minutes are required")
    .refine((v) => {
      const n = Number(v);
      return Number.isInteger(n) && n >= 1 && n <= MAX_DAY_MINUTES;
    }, `Enter whole minutes between 1 and ${MAX_DAY_MINUTES}`),
});

export const workReportFormSchema = z
  .object({
    report_date: z.string().min(1, "Date is required"),
    summary: z.string().max(SUMMARY_MAX, `Keep under ${SUMMARY_MAX} characters`),
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

export const EMPTY_TASK_ROW: WorkReportFormValues["tasks"][number] = {
  project_id: "",
  description: "",
  minutes_spent: "",
};

export const EMPTY_WORK_REPORT_FORM: WorkReportFormValues = {
  report_date: "",
  summary: "",
  tasks: [{ ...EMPTY_TASK_ROW }],
};

export const reviewNoteSchema = z.object({
  review_note: z
    .string()
    .min(1, "A reason is required")
    .max(REVIEW_NOTE_MAX, `Keep under ${REVIEW_NOTE_MAX} characters`),
});

export type ReviewNoteValues = z.infer<typeof reviewNoteSchema>;

const orNull = (v: string): string | null => (v.trim() === "" ? null : v);

function toTasks(v: WorkReportFormValues) {
  return v.tasks.map((t) => ({
    project_id: t.project_id,
    description: t.description.trim(),
    minutes_spent: Number(t.minutes_spent),
  }));
}

export function toCreateBody(v: WorkReportFormValues): WorkReportCreateBody {
  return {
    report_date: v.report_date,
    summary: orNull(v.summary),
    tasks: toTasks(v),
  };
}

/** WorkReportUpdate excludes report_date (immutable); tasks are replaced wholesale. */
export function toUpdateBody(v: WorkReportFormValues): WorkReportUpdateBody {
  return {
    summary: orNull(v.summary),
    tasks: toTasks(v),
  };
}

/** Map an existing report into editable form values (edit screen). */
export function toFormValues(report: WorkReport): WorkReportFormValues {
  return {
    report_date: report.report_date,
    summary: report.summary ?? "",
    tasks:
      report.tasks.length > 0
        ? report.tasks.map((t) => ({
            project_id: t.project_id,
            description: t.description,
            minutes_spent: String(t.minutes_spent),
          }))
        : [{ ...EMPTY_TASK_ROW }],
  };
}
