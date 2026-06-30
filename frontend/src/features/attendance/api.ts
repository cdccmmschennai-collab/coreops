import { api } from "@/lib/api-client";

import type {
  Attendance,
  AttendanceBulkSaveBody,
  AttendanceCreateBody,
  AttendanceListParams,
  AttendancePage,
  AttendanceSheet,
  AttendanceUpdateBody,
} from "./types";

function toQuery(p: AttendanceListParams): string {
  const sp = new URLSearchParams();
  if (p.employee_id) sp.set("employee_id", p.employee_id);
  if (p.status) sp.set("status", p.status);
  if (p.from) sp.set("from", p.from);
  if (p.to) sp.set("to", p.to);
  sp.set("limit", String(p.limit));
  sp.set("offset", String(p.offset));
  return sp.toString();
}

export const attendanceApi = {
  list: (params: AttendanceListParams) =>
    api.get<AttendancePage>(`/attendance?${toQuery(params)}`),
  get: (id: string) => api.get<Attendance>(`/attendance/${id}`),
  create: (body: AttendanceCreateBody) => api.post<Attendance>("/attendance", body),
  update: (id: string, body: AttendanceUpdateBody) =>
    api.patch<Attendance>(`/attendance/${id}`, body),
  remove: (id: string) => api.del<void>(`/attendance/${id}`),
  getSheet: (date: string) =>
    api.get<AttendanceSheet>(`/attendance/sheet?date=${date}`),
  bulkSave: (body: AttendanceBulkSaveBody) =>
    api.post<AttendanceSheet>("/attendance/bulk", body),
};
