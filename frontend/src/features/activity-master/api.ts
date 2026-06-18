import { api } from "@/lib/api-client";

import type { ActivityMaster, BenchmarkType, RelevantCountField, SubActivityFlat } from "./types";

export interface ActivityCreateBody {
  code?: string | null;
  name: string;
  sort_order?: number;
  is_active?: boolean;
}

export interface SubActivityCreateBody {
  code?: string | null;
  name: string;
  benchmark_type?: BenchmarkType | null;
  benchmark_value?: number | null;
  benchmark_period_days?: number | null;
  benchmark_unit_note?: string | null;
  benchmark_remarks?: string | null;
  relevant_count_field?: RelevantCountField | null;
  sort_order?: number;
  is_active?: boolean;
}

export type ActivityMasterUpdateBody = Partial<SubActivityCreateBody>;

function q(activeOnly?: boolean): string {
  return activeOnly === undefined ? "" : `?active_only=${activeOnly}`;
}

export const activityMasterApi = {
  listActivities: (activeOnly?: boolean) =>
    api.get<ActivityMaster[]>(`/activity-master/activities${q(activeOnly)}`),
  createActivity: (body: ActivityCreateBody) =>
    api.post<ActivityMaster>("/activity-master/activities", body),
  updateActivity: (id: string, body: ActivityMasterUpdateBody) =>
    api.patch<ActivityMaster>(`/activity-master/activities/${id}`, body),
  deactivateActivity: (id: string) => api.del<ActivityMaster>(`/activity-master/activities/${id}`),

  listSubActivities: (activityId: string, activeOnly?: boolean) =>
    api.get<ActivityMaster[]>(`/activity-master/activities/${activityId}/sub-activities${q(activeOnly)}`),
  createSubActivity: (activityId: string, body: SubActivityCreateBody) =>
    api.post<ActivityMaster>(`/activity-master/activities/${activityId}/sub-activities`, body),
  updateSubActivity: (id: string, body: ActivityMasterUpdateBody) =>
    api.patch<ActivityMaster>(`/activity-master/sub-activities/${id}`, body),
  deactivateSubActivity: (id: string) => api.del<ActivityMaster>(`/activity-master/sub-activities/${id}`),

  listAllSubActivitiesFlat: (activeOnly?: boolean) =>
    api.get<SubActivityFlat[]>(`/activity-master/sub-activities${q(activeOnly)}`),
};
