import { EmptyState } from "@/components/feedback/empty-state";

/**
 * Placeholder for the employee-facing Attendance Corrections workflow.
 *
 * Deferred: attendance is entered manually by the PM today — there is no
 * biometric / punch device or automated capture, so there is nothing to
 * correct. Only rendered when `features.attendanceCorrections` is enabled.
 * The real workflow (request form, review/approval, tables, APIs) is not
 * built yet; mock/sample rows were intentionally removed.
 */
export function CorrectionsPreview() {
  return (
    <EmptyState
      title="Attendance Corrections not available yet"
      description="Corrections will be enabled once biometric integration or automated attendance capture is in place. Attendance is currently recorded manually."
    />
  );
}
