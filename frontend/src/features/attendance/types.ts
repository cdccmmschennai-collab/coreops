import type { components } from "@/types/openapi";

// Types come straight from the live API contract (openapi-typescript output).
export type Attendance = components["schemas"]["AttendanceOut"];
export type AttendanceStatus = components["schemas"]["AttendanceStatus"];
export type AttendancePage = components["schemas"]["AttendancePage"];
export type AttendanceCreateBody = components["schemas"]["AttendanceCreate"];
export type AttendanceUpdateBody = components["schemas"]["AttendanceUpdate"];

// Bulk / sheet (PM roster workflow)
export type AttendanceSheet = components["schemas"]["AttendanceSheet"];
export type AttendanceSheetRow = components["schemas"]["AttendanceSheetRow"];
export type AttendanceBulkSaveBody = components["schemas"]["AttendanceBulkSave"];
export type AttendanceBulkRecord = components["schemas"]["AttendanceBulkRecord"];

// Bulk apply (one status over employees x dates; dry_run previews)
export type AttendanceBulkApplyBody = components["schemas"]["AttendanceBulkApply"];
export type AttendanceBulkApplyResult = components["schemas"]["AttendanceBulkApplyResult"];
export type AttendanceBulkApplyItem = components["schemas"]["AttendanceBulkApplyItem"];
export type AttendanceBulkApplyOutcome = AttendanceBulkApplyItem["outcome"];

export interface AttendanceListParams {
  employee_id: string;
  status: AttendanceStatus | "";
  from: string;
  to: string;
  limit: number;
  offset: number;
}
