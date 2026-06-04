/**
 * Client-side RBAC helper. Two system roles:
 *   project_manager — full system access
 *   employee        — basic user (own data + assigned projects)
 *
 * Project roles (team_lead / contributor / qc) are enforced at the API level.
 * This matrix controls UI gating only — the API is the source of truth.
 */
import type { Role } from "@/types/api";

export type Capability =
  | "user.manage"         // project_manager: Settings → Users & Roles
  | "employee.view"       // project_manager: navigate to /employees list
  | "employee.manage"     // project_manager: create/edit/deactivate employees
  | "project.view"        // project_manager: navigate to /projects list (employee sees assigned)
  | "project.manage"      // project_manager: create/edit/archive projects
  | "analytics.view"      // project_manager: aggregate analytics
  | "report.submit"       // both: create/edit/submit/delete own reports
  | "report.review"       // project_manager: approve/reject reports
  | "attendance.viewTeam" // project_manager: team attendance view
  | "attendance.manage"   // project_manager: create/edit/delete attendance records
  | "leave.request"       // employee: submit leave requests via UI
  | "leave.review"        // project_manager: approve/reject leave
  | "calendar.manage"     // project_manager: create/edit/delete company calendar events
  | "masterdata.manage";  // project_manager: manage activity types, job codes

const MATRIX: Record<Capability, Role[]> = {
  "user.manage":          ["project_manager"],
  "employee.view":        ["project_manager"],
  "employee.manage":      ["project_manager"],
  "project.view":         ["project_manager"],
  "project.manage":       ["project_manager"],
  "analytics.view":       ["project_manager"],
  "report.submit":        ["project_manager", "employee"],
  "report.review":        ["project_manager"],
  "attendance.viewTeam":  ["project_manager"],
  "attendance.manage":    ["project_manager"],
  "leave.request":        ["employee"],
  "leave.review":         ["project_manager"],
  "calendar.manage":      ["project_manager"],
  "masterdata.manage":    ["project_manager"],
};

export function can(role: Role | undefined, capability: Capability): boolean {
  if (!role) return false;
  const allowed = MATRIX[capability];
  if (!allowed) return false;
  return allowed.includes(role);
}

export function isManagerial(role: Role | undefined): boolean {
  return role === "project_manager";
}
