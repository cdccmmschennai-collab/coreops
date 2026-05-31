import { Badge } from "@/components/ui/badge";

import { STATUS_LABEL } from "../schemas";
import type { EmployeeStatus } from "../types";

const VARIANT: Record<EmployeeStatus, "success" | "warning" | "neutral"> = {
  active: "success",
  on_leave: "warning",
  exited: "neutral",
};

export function StatusBadge({ status }: { status: EmployeeStatus }) {
  return (
    <Badge variant={VARIANT[status]} dot>
      {STATUS_LABEL[status]}
    </Badge>
  );
}
