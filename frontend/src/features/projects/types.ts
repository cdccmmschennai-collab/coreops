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

export interface ProjectListParams {
  q: string;
  status: ProjectStatus | "";
  limit: number;
  offset: number;
}
