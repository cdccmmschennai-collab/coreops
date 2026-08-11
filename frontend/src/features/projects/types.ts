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

// Project Tag Scope — current scope + its append-only revision history, and the
// establish/revise body. The body carries only what a human decided (count,
// status, why); the revision number, previous_* values and author are derived
// server-side, which is why no such field exists on TagScopeUpdateBody.
export type TagScope = components["schemas"]["TagScopeOut"];
export type TagScopeRevision = components["schemas"]["TagScopeRevisionOut"];
export type TagScopeUpdateBody = components["schemas"]["TagScopeUpdate"];

// Summary tab: per-sub-activity progress against the project's tag scope. Every
// row carries the same estimated_tag_count - activities progress against the
// project's tag universe independently, so the rows never sum to it.
export type ProjectSummary = components["schemas"]["ProjectSummaryOut"];
export type TagScopeProgressRow = components["schemas"]["TagScopeProgressRow"];

// Weekly Report (Phase 7): every activity line reported on the project during
// one Fri-Thu cycle, for the assigned Head. Unlike Summary this is not limited
// to tag-counted work - the same payload backs the preview and the .xlsx.
export type WeeklyReport = components["schemas"]["WeeklyReportOut"];
export type WeeklyReportRow = components["schemas"]["WeeklyReportRow"];
export type WeeklyReportPeriod = components["schemas"]["WeeklyReportPeriodOut"];

// Phase 3 — per-activity staffing.
export type ActivityStaffing = components["schemas"]["ActivityStaffingOut"];
export type ActivityMember = components["schemas"]["ActivityMemberOut"];
export type ActivityMemberRole = components["schemas"]["ActivityMemberRole"];
export type ActivityMemberCreateBody = components["schemas"]["ActivityMemberCreate"];
export type ActivityMemberUpdateBody = components["schemas"]["ActivityMemberUpdate"];
// Candidate employees for the shared activity-assignment form (all active).
export type AssignableEmployee = components["schemas"]["EmployeeOut"];

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
