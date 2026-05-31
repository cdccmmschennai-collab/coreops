import type { AttendanceListParams } from "./types";

export const attendanceKeys = {
  all: ["attendance"] as const,
  list: (params: AttendanceListParams) => ["attendance", "list", params] as const,
  detail: (id: string) => ["attendance", "detail", id] as const,
};
