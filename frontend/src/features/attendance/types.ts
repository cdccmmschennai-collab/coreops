import type { components } from "@/types/openapi";

// Types come straight from the live API contract (openapi-typescript output).
export type Attendance = components["schemas"]["AttendanceOut"];
export type AttendanceStatus = components["schemas"]["AttendanceStatus"];
export type AttendancePage = components["schemas"]["AttendancePage"];
export type AttendanceCreateBody = components["schemas"]["AttendanceCreate"];
export type AttendanceUpdateBody = components["schemas"]["AttendanceUpdate"];

export interface AttendanceListParams {
  employee_id: string;
  status: AttendanceStatus | "";
  from: string;
  to: string;
  limit: number;
  offset: number;
}
