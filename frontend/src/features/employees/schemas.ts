import { z } from "zod";

import type { EmployeeCreateBody, EmployeeUpdateBody } from "./types";

export const EMPLOYEE_STATUSES = ["active", "on_leave", "exited"] as const;

export const STATUS_LABEL: Record<(typeof EMPLOYEE_STATUSES)[number], string> = {
  active: "Active",
  on_leave: "On leave",
  exited: "Exited",
};

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** Form shape (all text inputs are strings; selects hold uuid or ""). */
export const employeeFormSchema = z.object({
  employee_code: z.string().trim().min(1, "Employee number is required"),
  first_name: z.string().trim().min(1, "First name is required"),
  last_name: z.string().trim().min(1, "Last name is required"),
  work_email: z
    .string()
    .trim()
    .refine((v) => v === "" || EMAIL_PATTERN.test(v), "Enter a valid email"),
  phone: z.string().trim(),
  department: z.string().trim(),
  designation: z.string().trim(),
  date_of_joining: z.string(),
  status: z.enum(EMPLOYEE_STATUSES),
  manager_id: z.string(),
  user_id: z.string(),
});

export type EmployeeFormValues = z.infer<typeof employeeFormSchema>;

export const EMPTY_EMPLOYEE_FORM: EmployeeFormValues = {
  employee_code: "",
  first_name: "",
  last_name: "",
  work_email: "",
  phone: "",
  department: "",
  designation: "",
  date_of_joining: "",
  status: "active",
  manager_id: "",
  user_id: "",
};

const orNull = (v: string): string | null => (v.trim() === "" ? null : v.trim());

export function toCreateBody(v: EmployeeFormValues): EmployeeCreateBody {
  return {
    employee_code: v.employee_code,
    first_name: v.first_name,
    last_name: v.last_name,
    status: v.status,
    work_email: orNull(v.work_email),
    phone: orNull(v.phone),
    department: orNull(v.department),
    designation: orNull(v.designation),
    date_of_joining: orNull(v.date_of_joining),
    manager_id: orNull(v.manager_id),
    user_id: orNull(v.user_id),
  };
}

/** EmployeeUpdate excludes employee_code and user_id (not editable). */
export function toUpdateBody(v: EmployeeFormValues): EmployeeUpdateBody {
  return {
    first_name: v.first_name,
    last_name: v.last_name,
    status: v.status,
    work_email: orNull(v.work_email),
    phone: orNull(v.phone),
    department: orNull(v.department),
    designation: orNull(v.designation),
    date_of_joining: orNull(v.date_of_joining),
    manager_id: orNull(v.manager_id),
  };
}
