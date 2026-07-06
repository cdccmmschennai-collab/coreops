import type { components } from "@/types/openapi";

// Types come straight from the live API contract (openapi-typescript output).
export type Project = components["schemas"]["ProjectOut"];
export type ProjectStatus = components["schemas"]["ProjectStatus"];
export type ProjectPage = components["schemas"]["ProjectPage"];
export type ProjectCreateBody = components["schemas"]["ProjectCreate"];
export type ProjectUpdateBody = components["schemas"]["ProjectUpdate"];
export type ProjectMember = components["schemas"]["ProjectMemberOut"];
export type ProjectMemberRole = components["schemas"]["ProjectMemberRole"];
export type ProjectMemberCreateBody = components["schemas"]["ProjectMemberCreate"];
export type PlannedDateUpdateBody = components["schemas"]["PlannedDateUpdate"];
export type ProjectHeadUpdateBody = components["schemas"]["ProjectHeadUpdate"];
export type PlannedDateChange = components["schemas"]["PlannedDateChangeOut"];
export type ProjectTimelineEvent = components["schemas"]["TimelineEventOut"];

// Phase 3 — per-activity staffing.
export type ActivityStaffing = components["schemas"]["ActivityStaffingOut"];
export type ActivityMember = components["schemas"]["ActivityMemberOut"];
export type ActivityMemberRole = components["schemas"]["ActivityMemberRole"];
export type ActivityMemberCreateBody = components["schemas"]["ActivityMemberCreate"];
export type ActivityMemberUpdateBody = components["schemas"]["ActivityMemberUpdate"];

// Display labels for project member roles. Stored/API values are kept as-is
// (team_lead, contributor, qc) — only the rendered text differs.
// Keyed by the active roles only; legacy/unknown values fall back to the raw value
// via projectMemberRoleLabel().
export const PROJECT_MEMBER_ROLE_LABEL: Partial<Record<ProjectMemberRole, string>> = {
  team_lead: "Lead",
  contributor: "Contributor",
  qc: "QC",
};

export function projectMemberRoleLabel(role: ProjectMemberRole): string {
  return PROJECT_MEMBER_ROLE_LABEL[role] ?? role;
}

export interface ProjectListParams {
  q: string;
  status: ProjectStatus | "";
  limit: number;
  offset: number;
}
