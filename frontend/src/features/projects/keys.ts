import type { ProjectListParams } from "./types";

export const projectsKeys = {
  all: ["projects"] as const,
  list: (params: ProjectListParams) => ["projects", "list", params] as const,
  detail: (id: string) => ["projects", "detail", id] as const,
  members: (id: string) => ["projects", "members", id] as const,
};
