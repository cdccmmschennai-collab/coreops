import { Badge } from "@/components/ui/badge";

import {
  productionStatusLabel,
  resolveProductionStatus,
} from "../production-status";

/**
 * IN PROGRESS / CLOSED.
 *
 * Colour is chosen from the STORED value, never from the rendered label, so
 * rewording a label can never silently change what a colour means. An unknown
 * value from a newer backend renders neutral rather than disappearing.
 */
export function ProductionStatusBadge({ status }: { status: string | null | undefined }) {
  const value = resolveProductionStatus(status);
  return (
    <Badge
      variant={value === "closed" ? "success" : value === "in_progress" ? "warning" : "neutral"}
      dot
    >
      {productionStatusLabel(status)}
    </Badge>
  );
}
