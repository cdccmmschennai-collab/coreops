import { Badge } from "@/components/ui/badge";

import { USER_ROLE_LABEL } from "../schemas";
import type { UserRole } from "../types";

// Keyed by the active roles only; legacy/unknown values fall back to "neutral".
const VARIANT: Partial<Record<UserRole, "info" | "success" | "neutral">> = {
  project_manager: "info",
  employee: "neutral",
};

export function RoleBadge({ role }: { role: UserRole }) {
  const label =
    role in USER_ROLE_LABEL
      ? USER_ROLE_LABEL[role as keyof typeof USER_ROLE_LABEL]
      : role;
  return <Badge variant={VARIANT[role] ?? "neutral"}>{label}</Badge>;
}
