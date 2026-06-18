import { z } from "zod";

import type { UserCreateBody, UserUpdateBody } from "./types";

export const USER_ROLES = ["project_manager", "employee"] as const;

export const USER_ROLE_LABEL: Record<(typeof USER_ROLES)[number], string> = {
  project_manager: "Project Manager",
  employee: "Employee",
};

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

// ---------- create ----------
export const userCreateSchema = z.object({
  email: z.string().trim().min(1, "Email is required").regex(EMAIL_PATTERN, "Enter a valid email"),
  password: z.string().min(8, "Password must be at least 8 characters"),
  role: z.enum(USER_ROLES),
});

export type UserCreateValues = z.infer<typeof userCreateSchema>;

export const EMPTY_USER_CREATE: UserCreateValues = {
  email: "",
  password: "",
  role: "employee",
};

export function toCreateBody(v: UserCreateValues): UserCreateBody {
  return { email: v.email, password: v.password, role: v.role };
}

// ---------- edit ----------
export const userEditSchema = z.object({
  role: z.enum(USER_ROLES),
  status: z.enum(["active", "inactive"]),
});

export type UserEditValues = z.infer<typeof userEditSchema>;

export function toUpdateBody(v: UserEditValues): UserUpdateBody {
  return { role: v.role, is_active: v.status === "active" };
}

// ---------- reset password ----------
export const passwordSchema = z.object({
  new_password: z.string().min(8, "Password must be at least 8 characters"),
});

export type PasswordValues = z.infer<typeof passwordSchema>;
