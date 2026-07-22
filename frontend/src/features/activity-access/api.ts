import { api } from "@/lib/api-client";

import type {
  AccessType,
  ActivityAccessConfig,
  EmployeeSearchResult,
  GrantResult,
} from "./types";

interface EmployeePage {
  items: EmployeeSearchResult[];
  total: number;
  limit: number;
  offset: number;
}

const BASE = "/activity-master/activities";

export const activityAccessApi = {
  getConfig: (activityId: string, limit: number, offset: number) =>
    api.get<ActivityAccessConfig>(
      `${BASE}/${activityId}/access?limit=${limit}&offset=${offset}`,
    ),

  changeAccessType: (
    activityId: string,
    body: { access_type: AccessType; employee_ids?: string[] },
  ) => api.patch<GrantResult>(`${BASE}/${activityId}/access-type`, body),

  grant: (activityId: string, employeeIds: string[]) =>
    api.post<GrantResult>(`${BASE}/${activityId}/access`, {
      employee_ids: employeeIds,
    }),

  revoke: (activityId: string, employeeId: string) =>
    api.del<{ revoked: boolean; authorized_count: number }>(
      `${BASE}/${activityId}/access/${employeeId}`,
    ),

  // Server-side employee search for the grant picker. Only active employees,
  // capped at ~20, already-granted employees excluded server-side.
  searchEmployees: (activityId: string, q: string, signal?: AbortSignal) => {
    const sp = new URLSearchParams({
      q,
      status: "active",
      exclude_activity_id: activityId,
      limit: "20",
      offset: "0",
    });
    return api.get<EmployeePage>(`/employees?${sp.toString()}`, signal);
  },
};
