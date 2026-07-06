"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth/auth-provider";
import { useEmployees } from "@/features/employees/hooks";
import { AppError } from "@/lib/api-client";
import { can } from "@/lib/rbac";

import { useActivityStaffing, useSetProjectHead } from "../hooks";
import { type ActivityMember, type Project } from "../types";
import { ProjectRoleBadges, type ProjectRoleKey } from "./project-role-badges";

/** The effective role badges for one activity assignment: the base role plus,
 * additively, the QC badge when the person also holds QC. */
function assignmentRoles(member: ActivityMember): { role: ProjectRoleKey }[] {
  const roles: { role: ProjectRoleKey }[] = [{ role: member.role }];
  if (member.is_qc) roles.push({ role: "qc" });
  return roles;
}

function AssignmentRow({ member }: { member: ActivityMember }) {
  return (
    <li className="flex items-center justify-between gap-2 py-2 text-sm">
      <span className="min-w-0 truncate font-medium">{member.employee_name}</span>
      <ProjectRoleBadges
        roles={assignmentRoles(member)}
        className="flex flex-shrink-0 flex-wrap items-center justify-end gap-1.5"
      />
    </li>
  );
}

export function ProjectMembers({ project }: { project: Project }) {
  const { role } = useAuth();
  const canManage = can(role, "project.manage");
  const archived = project.status === "archived";
  const headEmployeeId = project.head_employee_id;

  const staffingQuery = useActivityStaffing(project.id);
  // Only activities with assignments come back — render each as its own section.
  const activities = staffingQuery.data ?? [];

  const setHead = useSetProjectHead(project.id);
  const [selectedHead, setSelectedHead] = React.useState("");

  // Head picker = any active employee (the backend auto-adds them as a member).
  const employeesQuery = useEmployees({
    q: "",
    status: "active",
    department: "",
    manager_id: "",
    limit: 100,
    offset: 0,
  });
  const headCandidates = (employeesQuery.data?.items ?? []).filter(
    (e) => e.id !== headEmployeeId,
  );

  async function assignHead() {
    if (!selectedHead) return;
    try {
      await setHead.mutateAsync({ head_employee_id: selectedHead });
      toast.success("Project Head assigned");
      setSelectedHead("");
    } catch (error) {
      toast.error(error instanceof AppError ? error.message : "Could not assign Head.");
    }
  }

  const hasHead = !!headEmployeeId && !!project.head_employee_name;
  const isEmpty = !hasHead && activities.length === 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Members ({project.member_count})</CardTitle>
      </CardHeader>
      <CardContent>
        {staffingQuery.isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-2/3" />
          </div>
        ) : isEmpty ? (
          <p className="text-sm text-muted-foreground">No members assigned.</p>
        ) : (
          <div className="space-y-4">
            {/* Project Head — always pinned to the top of the card. */}
            {hasHead && (
              <div>
                <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Project Head
                </p>
                <div className="flex items-center justify-between gap-2 py-2 text-sm">
                  <span className="min-w-0 truncate font-medium">
                    {project.head_employee_name}
                  </span>
                  <ProjectRoleBadges
                    roles={[{ role: "head" }]}
                    className="flex flex-shrink-0 items-center gap-1.5"
                  />
                </div>
              </div>
            )}

            {/* One section per assigned activity (Lead first, then Contributors). */}
            {activities.map((activity, idx) => (
              <div key={activity.activity_id}>
                {(hasHead || idx > 0) && <Separator className="mb-4" />}
                <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {activity.activity_code ?? activity.activity_name}
                </p>
                <ul className="divide-y divide-border">
                  {activity.lead && (
                    <AssignmentRow key={activity.lead.id} member={activity.lead} />
                  )}
                  {(activity.contributors ?? []).map((c) => (
                    <AssignmentRow key={c.id} member={c} />
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}

        {/* PM only assigns / changes the Project Head. Lead / Contributor / QC
            are activity-level and assigned by the Head in the Activities card. */}
        {canManage && !archived && (
          <>
            <Separator className="my-4" />
            <p className="mb-2 text-sm font-medium">Assign / Change Head</p>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <Select value={selectedHead} onValueChange={setSelectedHead}>
                <SelectTrigger className="sm:flex-1">
                  <SelectValue placeholder="Select an employee…" />
                </SelectTrigger>
                <SelectContent>
                  {headCandidates.length === 0 ? (
                    <div className="px-2 py-1.5 text-sm text-muted-foreground">
                      No employees available
                    </div>
                  ) : (
                    headCandidates.map((e) => (
                      <SelectItem key={e.id} value={e.id}>
                        {e.full_name} · {e.employee_code}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
              <Button
                onClick={() => void assignHead()}
                disabled={!selectedHead}
                loading={setHead.isPending}
              >
                {headEmployeeId ? "Change Head" : "Assign Head"}
              </Button>
            </div>
          </>
        )}

        {archived && (
          <p className="mt-3 text-xs text-muted-foreground">
            Archived projects can't be modified.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
