/**
 * Client-side RBAC helper. Mirrors the API permission matrix
 * (V1_ARCHITECTURE_PACKAGE.md §7). UX only — the API is the source of truth.
 */
import type { Role } from "@/types/api";

export type Capability =
  | "user.manage" // admin: Settings → Users & Roles
  | "employee.manage" // admin: create/edit employees
  | "project.manage" // admin: create/edit/archive projects
  | "report.review" // manager/admin: approve/reject reports
  | "attendance.viewTeam" // manager/admin: team attendance
  | "attendance.manage"; // admin: create/edit/delete attendance records

const MATRIX: Record<Capability, Role[]> = {
  "user.manage": ["admin"],
  "employee.manage": ["admin"],
  "project.manage": ["admin"],
  "report.review": ["admin", "manager"],
  "attendance.viewTeam": ["admin", "manager"],
  "attendance.manage": ["admin"],
};

export function can(role: Role | undefined, capability: Capability): boolean {
  if (!role) return false;
  return MATRIX[capability].includes(role);
}

export function isManagerial(role: Role | undefined): boolean {
  return role === "admin" || role === "manager";
}
