import { z } from "zod";

import type { TaskCreateBody, TaskPriority, TaskStatus, TaskUpdateBody } from "./types";

export const TASK_STATUSES = ["open", "in_progress", "completed", "cancelled"] as const;
export const TASK_PRIORITIES = ["low", "medium", "high"] as const;

export const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  completed: "Completed",
  cancelled: "Cancelled",
};

export const TASK_PRIORITY_LABEL: Record<TaskPriority, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
};

export const EMPLOYEE_TASK_STATUSES = ["open", "in_progress", "completed"] as const;

export const taskFormSchema = z.object({
  title: z.string().trim().min(1, "Title is required"),
  description: z.string().trim(),
  // Team leads assign within a project; PMs leave this blank.
  project_id: z.string(),
  assigned_to_employee_id: z.string().min(1, "Assignee is required"),
  priority: z.enum(TASK_PRIORITIES),
  due_date: z.string(),
});

export type TaskFormValues = z.infer<typeof taskFormSchema>;

export const EMPTY_TASK_FORM: TaskFormValues = {
  title: "",
  description: "",
  project_id: "",
  assigned_to_employee_id: "",
  priority: "medium",
  due_date: "",
};

const orNull = (v: string): string | null => (v.trim() === "" ? null : v.trim());

export function toCreateBody(v: TaskFormValues): TaskCreateBody {
  return {
    title: v.title,
    description: orNull(v.description),
    assigned_to_employee_id: v.assigned_to_employee_id,
    project_id: orNull(v.project_id),
    priority: v.priority,
    due_date: orNull(v.due_date),
  };
}

export function toUpdateBody(v: TaskFormValues): TaskUpdateBody {
  return {
    title: v.title,
    description: orNull(v.description),
    assigned_to_employee_id: v.assigned_to_employee_id,
    priority: v.priority,
    due_date: orNull(v.due_date),
  };
}
