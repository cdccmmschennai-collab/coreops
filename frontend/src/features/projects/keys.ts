import type { ProjectListParams } from "./types";

export const projectsKeys = {
  all: ["projects"] as const,
  list: (params: ProjectListParams) => ["projects", "list", params] as const,
  detail: (id: string) => ["projects", "detail", id] as const,
  members: (id: string) => ["projects", "members", id] as const,
  activityStaffing: (id: string) => ["projects", "activity-staffing", id] as const,
  assignableEmployees: (id: string) =>
    ["projects", "assignable-employees", id] as const,
  plannedDateChanges: (id: string) => ["projects", "planned-date-changes", id] as const,
  timeline: (id: string) => ["projects", "timeline", id] as const,
};
