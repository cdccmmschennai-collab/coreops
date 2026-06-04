import { z } from "zod";

import type { ProjectCreateBody, ProjectUpdateBody } from "./types";

export const PROJECT_STATUSES = [
  "planning",
  "active",
  "on_hold",
  "completed",
  "archived",
] as const;

export const PROJECT_STATUS_LABEL: Record<(typeof PROJECT_STATUSES)[number], string> = {
  planning: "Planning",
  active: "Active",
  on_hold: "On hold",
  completed: "Completed",
  archived: "Archived",
};

export const projectFormSchema = z
  .object({
    code: z.string().trim().min(1, "Project code is required"),
    name: z.string().trim().min(1, "Project name is required"),
    job_code_id: z.string().optional().default(""),
    client: z.string().trim(),
    description: z.string().trim(),
    status: z.enum(PROJECT_STATUSES),
    start_date: z.string(),
    end_date: z.string(),
  })
  .refine(
    (v) => !(v.start_date && v.end_date) || v.end_date >= v.start_date,
    { message: "End date cannot be before start date", path: ["end_date"] },
  );

export type ProjectFormValues = z.infer<typeof projectFormSchema>;

export const EMPTY_PROJECT_FORM: ProjectFormValues = {
  code: "",
  name: "",
  job_code_id: "",
  client: "",
  description: "",
  status: "planning",
  start_date: "",
  end_date: "",
};

const orNull = (v: string): string | null => (v.trim() === "" ? null : v.trim());

const orNullUuid = (v: string | undefined): string | null =>
  !v || v.trim() === "" ? null : v.trim();

export function toCreateBody(v: ProjectFormValues): ProjectCreateBody {
  return {
    code: v.code,
    name: v.name,
    job_code_id: orNullUuid(v.job_code_id),
    status: v.status,
    client: orNull(v.client),
    description: orNull(v.description),
    start_date: orNull(v.start_date),
    end_date: orNull(v.end_date),
  };
}

/** ProjectUpdate excludes code (immutable). */
export function toUpdateBody(v: ProjectFormValues): ProjectUpdateBody {
  return {
    name: v.name,
    job_code_id: orNullUuid(v.job_code_id),
    status: v.status,
    client: orNull(v.client),
    description: orNull(v.description),
    start_date: orNull(v.start_date),
    end_date: orNull(v.end_date),
  };
}
