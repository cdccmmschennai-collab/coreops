import { z } from "zod";

import type { DeliverableCreateBody, DeliverableUpdateBody } from "./types";

export const DELIVERABLE_STATUSES = ["pending", "in_progress", "completed"] as const;

export const deliverableFormSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(500),
  description: z.string().trim().optional(),
  planned_start_date: z.string().optional(),
  target_date: z.string().optional(),
  owner_employee_id: z.string().optional(),
  status: z.enum(DELIVERABLE_STATUSES),
  completion_date: z.string().optional(),
  // Mandatory only when editing a tracked field (planned start / due date /
  // status reversal). Enforced contextually by the form, not the schema.
  reason: z.string().optional(),
});

export type DeliverableFormValues = z.infer<typeof deliverableFormSchema>;

export const EMPTY_DELIVERABLE_FORM: DeliverableFormValues = {
  name: "",
  description: "",
  planned_start_date: "",
  target_date: "",
  owner_employee_id: "",
  status: "pending",
  completion_date: "",
  reason: "",
};

function nullIfEmpty(v: string | undefined): string | null {
  return v && v.trim() ? v.trim() : null;
}

export function toCreateBody(v: DeliverableFormValues): DeliverableCreateBody {
  return {
    name: v.name.trim(),
    description: nullIfEmpty(v.description),
    planned_start_date: nullIfEmpty(v.planned_start_date),
    target_date: nullIfEmpty(v.target_date),
    owner_employee_id: nullIfEmpty(v.owner_employee_id),
    status: v.status,
    completion_date: nullIfEmpty(v.completion_date),
  };
}

export function toUpdateBody(v: DeliverableFormValues): DeliverableUpdateBody {
  return {
    name: v.name.trim(),
    description: nullIfEmpty(v.description),
    planned_start_date: nullIfEmpty(v.planned_start_date),
    target_date: nullIfEmpty(v.target_date),
    owner_employee_id: nullIfEmpty(v.owner_employee_id),
    status: v.status,
    completion_date: nullIfEmpty(v.completion_date),
    reason: nullIfEmpty(v.reason) ?? undefined,
  };
}

// ---------------------------------------------------------------------------
// Timeline edit (tracked fields — reason mandatory)
// ---------------------------------------------------------------------------

export const deliverableTimelineSchema = z.object({
  planned_start_date: z.string().optional(),
  target_date: z.string().optional(),
  status: z.enum(DELIVERABLE_STATUSES),
  reason: z.string().trim().min(1, "Reason is required").max(500),
});

export type DeliverableTimelineFormValues = z.infer<typeof deliverableTimelineSchema>;

export function toTimelineUpdateBody(
  v: DeliverableTimelineFormValues,
): DeliverableUpdateBody {
  return {
    planned_start_date: nullIfEmpty(v.planned_start_date),
    target_date: nullIfEmpty(v.target_date),
    status: v.status,
    reason: v.reason.trim(),
  };
}
