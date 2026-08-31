import { Badge } from "@/components/ui/badge";

import { isAutoReport } from "../report-origin";
import { WORK_REPORT_STATUS_LABEL } from "../schemas";
import type { WorkReportStatus } from "../types";

const VARIANT: Record<WorkReportStatus, "success" | "danger" | "warning" | "info" | "neutral"> = {
  draft: "neutral",
  submitted: "info",
  approved: "success",
  rejected: "danger",
  granted: "warning",
};

/**
 * Status pill for a work report. A submitted report that has a pending edit
 * request renders as a distinct "Requested" state (teal) instead of
 * "Submitted", so both the author and the Project Head can spot reports awaiting
 * an edit decision straight from the list — without relying on the
 * notification. "Requested" is display-only: the report's real status stays
 * `submitted` until the Head grants the edit (or, if they are the Head, edits it
 * directly).
 */
export function StatusBadge({
  status,
  editRequested = false,
}: {
  status: WorkReportStatus;
  editRequested?: boolean;
}) {
  if (status === "submitted" && editRequested) {
    return (
      <Badge variant="teal" dot>
        Requested
      </Badge>
    );
  }
  return (
    <Badge variant={VARIANT[status]} dot>
      {WORK_REPORT_STATUS_LABEL[status]}
    </Badge>
  );
}

/**
 * "AUTO" pill for a report the 01:00 generator produced instead of the employee
 * - a week-off day, or a day covered by approved leave. Purely informational:
 * it says where the row came from and changes nothing about who may edit it,
 * which the API alone decides.
 *
 * Rendered next to the status pill rather than replacing it, because the two
 * answer different questions ("Submitted" vs "nobody typed this"). Outline
 * variant keeps it quieter than the coloured status pill it sits beside.
 *
 * Renders nothing unless `origin` is exactly "auto" - see isAutoReport.
 */
export function AutoBadge({ origin }: { origin?: string | null }) {
  if (!isAutoReport({ origin })) return null;
  return (
    <Badge variant="outline" title="Generated automatically by the system">
      AUTO
    </Badge>
  );
}
