import { Badge } from "@/components/ui/badge";

import { PROJECT_STATUS_LABEL } from "../schemas";
import type { ProjectStatus } from "../types";

const VARIANT: Record<ProjectStatus, "neutral" | "info" | "success" | "warning"> = {
  planning: "neutral",
  active: "success",
  on_hold: "warning",
  completed: "info",
  archived: "neutral",
};

export function StatusBadge({ status }: { status: ProjectStatus }) {
  return (
    <Badge variant={VARIANT[status]} dot>
      {PROJECT_STATUS_LABEL[status]}
    </Badge>
  );
}
