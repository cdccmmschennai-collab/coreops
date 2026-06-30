import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { attendanceApi } from "./api";
import { attendanceKeys } from "./keys";
import type {
  AttendanceBulkSaveBody,
  AttendanceCreateBody,
  AttendanceListParams,
  AttendanceUpdateBody,
} from "./types";

export function useAttendanceList(params: AttendanceListParams) {
  return useQuery({
    queryKey: attendanceKeys.list(params),
    queryFn: () => attendanceApi.list(params),
    placeholderData: (prev) => prev,
  });
}

export function useAttendance(id: string | undefined, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: attendanceKeys.detail(id ?? ""),
    queryFn: () => attendanceApi.get(id as string),
    enabled: (options?.enabled ?? true) && !!id,
  });
}

export function useCreateAttendance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AttendanceCreateBody) => attendanceApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: attendanceKeys.all }),
  });
}

export function useUpdateAttendance(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AttendanceUpdateBody) => attendanceApi.update(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: attendanceKeys.all });
      qc.invalidateQueries({ queryKey: attendanceKeys.detail(id) });
    },
  });
}

export function useDeleteAttendance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => attendanceApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: attendanceKeys.all }),
  });
}

/** The PM roster sheet for a date (active employees merged with saved records).
 * Disabled until a date is chosen. */
export function useAttendanceSheet(date: string | undefined) {
  return useQuery({
    queryKey: attendanceKeys.sheet(date ?? ""),
    queryFn: () => attendanceApi.getSheet(date as string),
    enabled: !!date,
  });
}

export function useBulkSaveAttendance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AttendanceBulkSaveBody) => attendanceApi.bulkSave(body),
    onSuccess: (data) => {
      // Refresh lists/calendar and seed the sheet cache with the saved state.
      qc.invalidateQueries({ queryKey: attendanceKeys.all });
      qc.setQueryData(attendanceKeys.sheet(data.attendance_date), data);
    },
  });
}
