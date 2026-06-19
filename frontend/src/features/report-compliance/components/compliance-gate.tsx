"use client";

import { DailyReportReminder } from "./daily-report-reminder";
import { PendingReportsBanner } from "./pending-reports-banner";

/**
 * Mounts the employee report-compliance surfaces (login banner + 5:15 reminder).
 * Both internally no-op for managerial users and when there is nothing pending,
 * so it's safe to render once for every authenticated user. The banner renders
 * inline (returned first); the reminder is a portalled dialog.
 */
export function ComplianceGate() {
  return (
    <>
      <PendingReportsBanner />
      <DailyReportReminder />
    </>
  );
}
