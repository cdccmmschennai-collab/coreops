export interface EmployeeCompliance {
  has_attendance_today: boolean;
  has_report_today: boolean;
  pending_count: number;
  pending_dates: string[];
}
