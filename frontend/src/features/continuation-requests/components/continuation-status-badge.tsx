import { Badge } from "@/components/ui/badge";

import { CONTINUATION_STATUS_LABEL } from "../types";
import type { ContinuationRequestStatus } from "../types";

const VARIANT: Record<ContinuationRequestStatus, "neutral" | "success" | "warning" | "danger"> = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
};

export function ContinuationStatusBadge({ status }: { status: ContinuationRequestStatus }) {
  return (
    <Badge variant={VARIANT[status] ?? "neutral"}>
      {CONTINUATION_STATUS_LABEL[status] ?? status}
    </Badge>
  );
}
