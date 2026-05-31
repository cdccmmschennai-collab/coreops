import { z } from "zod";

import type { AttendanceCreateBody, AttendanceUpdateBody } from "./types";

export const ATTENDANCE_STATUSES = [
  "present",
  "absent",
  "half_day",
  "leave",
  "holiday",
  "weekend",
] as const;

export const ATTENDANCE_STATUS_LABEL: Record<(typeof ATTENDANCE_STATUSES)[number], string> = {
  present: "Present",
  absent: "Absent",
  half_day: "Half day",
  leave: "Leave",
  holiday: "Holiday",
  weekend: "Weekend",
};

export const attendanceFormSchema = z
  .object({
    employee_id: z.string().min(1, "Employee is required"),
    attendance_date: z.string().min(1, "Date is required"),
    status: z.enum(ATTENDANCE_STATUSES),
    check_in_at: z.string(),
    check_out_at: z.string(),
  })
  .refine(
    (v) => !(v.check_in_at && v.check_out_at) || v.check_out_at >= v.check_in_at,
    { message: "Check-out cannot be before check-in", path: ["check_out_at"] },
  );

export type AttendanceFormValues = z.infer<typeof attendanceFormSchema>;

export const EMPTY_ATTENDANCE_FORM: AttendanceFormValues = {
  employee_id: "",
  attendance_date: "",
  status: "present",
  check_in_at: "",
  check_out_at: "",
};

const orNull = (v: string): string | null => (v.trim() === "" ? null : v);

export function toCreateBody(v: AttendanceFormValues): AttendanceCreateBody {
  return {
    employee_id: v.employee_id,
    attendance_date: v.attendance_date,
    status: v.status,
    check_in_at: orNull(v.check_in_at),
    check_out_at: orNull(v.check_out_at),
  };
}

/** AttendanceUpdate excludes employee_id and attendance_date (immutable). */
export function toUpdateBody(v: AttendanceFormValues): AttendanceUpdateBody {
  return {
    status: v.status,
    check_in_at: orNull(v.check_in_at),
    check_out_at: orNull(v.check_out_at),
  };
}
