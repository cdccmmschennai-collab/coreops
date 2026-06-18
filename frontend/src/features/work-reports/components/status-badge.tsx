import { Badge } from "@/components/ui/badge";

import { WORK_REPORT_STATUS_LABEL } from "../schemas";
import type { WorkReportStatus } from "../types";

const VARIANT: Record<WorkReportStatus, "success" | "danger" | "warning" | "info" | "neutral"> = {
  draft: "neutral",
  submitted: "info",
  approved: "success",
  rejected: "danger",
  granted: "warning",
};

export function StatusBadge({ status }: { status: WorkReportStatus }) {
  return (
    <Badge variant={VARIANT[status]} dot>
      {WORK_REPORT_STATUS_LABEL[status]}
    </Badge>
  );
}
