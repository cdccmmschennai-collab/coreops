import { Badge } from "@/components/ui/badge";

export function UserStatusBadge({ active }: { active: boolean }) {
  return (
    <Badge variant={active ? "success" : "neutral"} dot>
      {active ? "Active" : "Inactive"}
    </Badge>
  );
}
