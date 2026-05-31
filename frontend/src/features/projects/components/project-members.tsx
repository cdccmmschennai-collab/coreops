"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { useProjectMembers } from "../hooks";
import type { Project } from "../types";

export function ProjectMembers({ project }: { project: Project }) {
  const query = useProjectMembers(project.id);
  const members = query.data ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Members ({project.member_count})</CardTitle>
      </CardHeader>
      <CardContent>
        {query.isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-2/3" />
          </div>
        ) : members.length === 0 ? (
          <p className="text-sm text-muted-foreground">No members assigned.</p>
        ) : (
          <ul className="divide-y divide-border">
            {members.map((m) => (
              <li key={m.id} className="flex items-center justify-between py-2 text-sm">
                <span className="font-medium">{m.employee_name}</span>
                <Badge variant={m.role === "lead" ? "info" : "neutral"}>{m.role}</Badge>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
