import { api } from "@/lib/api-client";
import type { ActivityType, ActivityTypePage, ActivityTypeListParams } from "./types";

function toQuery(p: ActivityTypeListParams): string {
  const sp = new URLSearchParams();
  if (p.category) sp.set("category", p.category);
  if (p.requires_project !== undefined) sp.set("requires_project", String(p.requires_project));
  if (p.active_only !== undefined) sp.set("active_only", String(p.active_only));
  sp.set("limit", String(p.limit ?? 200));
  sp.set("offset", String(p.offset ?? 0));
  return sp.toString();
}

export const activityTypesApi = {
  list: (params: ActivityTypeListParams = {}) =>
    api.get<ActivityTypePage>(`/activity-types?${toQuery(params)}`),
  get: (id: string) => api.get<ActivityType>(`/activity-types/${id}`),
};
