import { Badge } from "@/components/ui/badge";

import { DELIVERABLE_STATUS_LABEL, type DeliverableStatus } from "../types";

const VARIANT: Record<DeliverableStatus, "warning" | "success"> = {
  // Planned reuses the former "In Progress" styling; Completed is unchanged.
  planned: "warning",
  completed: "success",
};

export function DeliverableStatusBadge({ status }: { status: DeliverableStatus }) {
  return (
    <Badge variant={VARIANT[status]} dot>
      {DELIVERABLE_STATUS_LABEL[status]}
    </Badge>
  );
}
