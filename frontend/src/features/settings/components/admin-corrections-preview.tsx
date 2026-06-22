import { EmptyState } from "@/components/feedback/empty-state";

/**
 * Placeholder for the admin/PM-facing Attendance Corrections review queue.
 *
 * Deferred alongside the employee-facing workflow: with manual attendance
 * entry and no automated capture there are no correction requests to review.
 * Not currently wired into Settings; kept as a placeholder for the future
 * implementation. Mock/sample request rows were intentionally removed.
 */
export function AdminCorrectionsPreview() {
  return (
    <EmptyState
      title="Attendance Corrections not available yet"
      description="The review queue will be enabled once biometric integration or automated attendance capture is in place."
    />
  );
}
