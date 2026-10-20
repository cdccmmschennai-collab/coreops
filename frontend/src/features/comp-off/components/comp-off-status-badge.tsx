import { Badge } from "@/components/ui/badge";

import { COMP_OFF_STATUS_LABEL, COMP_OFF_STATUS_VARIANT, type CompOffStatus } from "../types";

export function CompOffStatusBadge({ status }: { status: CompOffStatus }) {
  return (
    <Badge variant={COMP_OFF_STATUS_VARIANT[status] ?? "neutral"}>
      {COMP_OFF_STATUS_LABEL[status] ?? status}
    </Badge>
  );
}
