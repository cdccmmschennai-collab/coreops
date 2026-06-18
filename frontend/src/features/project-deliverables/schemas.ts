import { z } from "zod";

import type { DeliverableCreateBody, DeliverableUpdateBody } from "./types";

export const DELIVERABLE_STATUSES = ["pending", "in_progress", "completed"] as const;

export const deliverableFormSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(500),
  description: z.string().trim().optional(),
  target_date: z.string().optional(),
  owner_employee_id: z.string().optional(),
  status: z.enum(DELIVERABLE_STATUSES),
  completion_date: z.string().optional(),
});

export type DeliverableFormValues = z.infer<typeof deliverableFormSchema>;

export const EMPTY_DELIVERABLE_FORM: DeliverableFormValues = {
  name: "",
  description: "",
  target_date: "",
  owner_employee_id: "",
  status: "pending",
  completion_date: "",
};

function nullIfEmpty(v: string | undefined): string | null {
  return v && v.trim() ? v.trim() : null;
}

export function toCreateBody(v: DeliverableFormValues): DeliverableCreateBody {
  return {
    name: v.name.trim(),
    description: nullIfEmpty(v.description),
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
    target_date: nullIfEmpty(v.target_date),
    owner_employee_id: nullIfEmpty(v.owner_employee_id),
    status: v.status,
    completion_date: nullIfEmpty(v.completion_date),
  };
}
