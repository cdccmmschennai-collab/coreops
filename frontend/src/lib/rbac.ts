/**
 * Client-side RBAC helper. Mirrors the API permission matrix
 * (V1_ARCHITECTURE_PACKAGE.md §7). UX only — the API is the source of truth.
 */
import type { Role } from "@/types/api";

export type Capability =
  | "user.manage"       // admin: Settings → Users & Roles
  | "employee.view"     // admin + manager: navigate to /employees list
  | "employee.manage"   // admin: create/edit/deactivate employees
  | "project.view"      // admin + manager: navigate to /projects list
  | "project.manage"    // admin: create/edit/archive projects
  | "analytics.view"    // admin + manager: aggregate analytics
  | "report.submit"     // admin/manager/employee: create/edit/submit/delete own reports
  | "report.review"     // manager/admin: approve/reject reports
  | "attendance.viewTeam" // manager/admin: team attendance
  | "attendance.manage"; // admin: create/edit/delete attendance records

const MATRIX: Record<Capability, Role[]> = {
  "user.manage":          ["admin"],
  "employee.view":        ["admin", "manager"],
  "employee.manage":      ["admin"],
  "project.view":         ["admin", "manager"],
  "project.manage":       ["admin"],
  "analytics.view":       ["admin", "manager"],
  "report.submit":        ["admin", "manager", "employee"],
  "report.review":        ["admin", "manager"],
  "attendance.viewTeam":  ["admin", "manager"],
  "attendance.manage":    ["admin"],
};

export function can(role: Role | undefined, capability: Capability): boolean {
  if (!role) return false;
  const allowed = MATRIX[capability];
  // Fail-closed: unknown capability → deny. Guards against stale bundles and
  // future callers passing a capability not yet added to MATRIX.
  if (!allowed) return false;
  return allowed.includes(role);
}

export function isManagerial(role: Role | undefined): boolean {
  return role === "admin" || role === "manager";
}
