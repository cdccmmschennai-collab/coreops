import { Badge } from "@/components/ui/badge";

import { USER_ROLE_LABEL } from "../schemas";
import type { UserRole } from "../types";

const VARIANT: Record<UserRole, "info" | "success" | "neutral"> = {
  project_manager: "info",
  employee: "neutral",
};

export function RoleBadge({ role }: { role: UserRole }) {
  return <Badge variant={VARIANT[role]}>{USER_ROLE_LABEL[role]}</Badge>;
}
