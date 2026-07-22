import { Lock, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";

import type { AccessType } from "../types";

/** Compact Common / Restricted badge for the Activity Master table. */
export function ActivityAccessBadge({ accessType }: { accessType: AccessType }) {
  if (accessType === "RESTRICTED") {
    return (
      <Badge variant="warning">
        <Lock className="h-3 w-3" aria-hidden />
        Restricted
      </Badge>
    );
  }
  return (
    <Badge variant="outline">
      <Users className="h-3 w-3" aria-hidden />
      Common
    </Badge>
  );
}
