export interface EmployeeCompliance {
  has_attendance_today: boolean;
  has_report_today: boolean;
  pending_count: number;
  pending_dates: string[];
  // Split-day fractions (warn-only, additive). reported = summed working
  // fractions of today's submitted report; attendance = 1.0 present / 0.5
  // half_day / null unknown. A mismatch flags the report as possibly
  // incomplete — it never blocks anything.
  reported_work_fraction_today: number | null;
  attendance_work_fraction_today: number | null;
  fraction_mismatch_today: boolean;
}
