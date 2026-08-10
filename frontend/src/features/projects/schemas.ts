import { z } from "zod";

// Relative .ts value import — the node --test harness resolves it directly.
import {
  DEFAULT_PROJECT_SCOPE_TYPE,
  parseTagCount,
  PROJECT_SCOPE_TYPES,
  REASON_REQUIRED_ERROR,
  TAG_COUNT_ERROR,
} from "./scope.ts";
import type { ProjectCreateBody, ProjectUpdateBody, TagScopeUpdateBody } from "./types";

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
    job_code: z.string().trim().optional().default(""),
    // A project belongs to a Planning Plant (project master). Description (PP)
    // is display-only, derived client-side from the selected Planning Plant.
    planning_plant_id: z.string().optional().default(""),
    // Maintenance Plant — scoped to the selected Planning Plant's plants.
    maintenance_plant_id: z.string().optional().default(""),
    client: z.string().trim(),
    description: z.string().trim(),
    status: z.enum(PROJECT_STATUSES),
    // Classification only: whether this project takes part in Project Tag Scope.
    scope_type: z.enum(PROJECT_SCOPE_TYPES),
    start_date: z.string(),
    planned_completion_date: z.string(),
    actual_completion_date: z.string(),
  })
  .refine(
    (v) =>
      !(v.start_date && v.planned_completion_date) ||
      v.planned_completion_date >= v.start_date,
    {
      message: "Planned completion date cannot be before start date",
      path: ["planned_completion_date"],
    },
  );

export type ProjectFormValues = z.infer<typeof projectFormSchema>;

export const EMPTY_PROJECT_FORM: ProjectFormValues = {
  code: "",
  name: "",
  job_code: "",
  planning_plant_id: "",
  maintenance_plant_id: "",
  client: "",
  description: "",
  status: "planning",
  scope_type: DEFAULT_PROJECT_SCOPE_TYPE,
  start_date: "",
  planned_completion_date: "",
  actual_completion_date: "",
};

const orNull = (v: string): string | null => (v.trim() === "" ? null : v.trim());

export function toCreateBody(v: ProjectFormValues): ProjectCreateBody {
  return {
    code: v.code,
    name: v.name,
    job_code: orNull(v.job_code),
    planning_plant_id: orNull(v.planning_plant_id),
    maintenance_plant_id: orNull(v.maintenance_plant_id),
    status: v.status,
    scope_type: v.scope_type,
    client: orNull(v.client),
    description: orNull(v.description),
    start_date: orNull(v.start_date),
    planned_completion_date: orNull(v.planned_completion_date),
    actual_completion_date: orNull(v.actual_completion_date),
  };
}

/** code is editable — the PM can fix a code entered before this field
 *  existed (still subject to the same uniqueness rule create enforces).
 *  planned_completion_date is included but the backend only applies it when
 *  the project has no existing planned date (initial set). Use
 *  PATCH /planned-completion-date for subsequent changes (requires a reason). */
export function toUpdateBody(v: ProjectFormValues): ProjectUpdateBody {
  return {
    code: v.code,
    name: v.name,
    job_code: orNull(v.job_code),
    planning_plant_id: orNull(v.planning_plant_id),
    maintenance_plant_id: orNull(v.maintenance_plant_id),
    status: v.status,
    scope_type: v.scope_type,
    client: orNull(v.client),
    description: orNull(v.description),
    start_date: orNull(v.start_date),
    planned_completion_date: orNull(v.planned_completion_date),
    actual_completion_date: orNull(v.actual_completion_date),
  };
}

export const plannedDateSchema = z.object({
  new_date: z.string(),
  reason: z.string().trim().min(1, "Reason is required").max(500),
});

export type PlannedDateFormValues = z.infer<typeof plannedDateSchema>;

// ---------- tag scope (Phase 4) ----------

/**
 * The Set / Revise Tag Scope form.
 *
 * The count is held as a string because that is what an <input> gives us, and
 * because `valueAsNumber` turns "abc" into NaN — indistinguishable from empty.
 * `parseTagCount` is the single definition of a valid count, shared with the
 * Save-button state, so the field and the button can never disagree.
 *
 * `requireReason` is a parameter rather than a second schema: the rule is the
 * backend's (mandatory when revising an established scope, defaulted to
 * "Initial project estimate" for the first one), and this mirrors it exactly.
 */
export function tagScopeFormSchema(requireReason: boolean) {
  return z.object({
    estimated_tag_count: z
      .string()
      .refine((v) => parseTagCount(v) !== null, { message: TAG_COUNT_ERROR }),
    status: z.enum(["PROVISIONAL", "BASELINED"]),
    reason: requireReason
      ? z.string().trim().min(1, REASON_REQUIRED_ERROR).max(500)
      : z.string().trim().max(500),
  });
}

export type TagScopeFormValues = z.infer<ReturnType<typeof tagScopeFormSchema>>;

/**
 * Form values -> PUT body. `expected_revision` is the revision the form was
 * opened against, so the server can refuse a save built on a view somebody else
 * has already superseded. The new revision number is never sent — the backend
 * owns it.
 */
export function toTagScopeBody(
  v: TagScopeFormValues,
  expectedRevision: number,
): TagScopeUpdateBody {
  const reason = v.reason.trim();
  return {
    // Non-null by construction: the schema rejects anything parseTagCount
    // refuses, so this branch is only reached with a valid count.
    estimated_tag_count: parseTagCount(v.estimated_tag_count) ?? 0,
    status: v.status,
    reason: reason === "" ? null : reason,
    expected_revision: expectedRevision,
  };
}
