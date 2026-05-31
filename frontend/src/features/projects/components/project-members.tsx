"use client";

import * as React from "react";
import { UserMinus } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
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

import {
  useAddMember,
  useProjectMembers,
  useRemoveMember,
  useUpdateMemberRole,
} from "../hooks";
import type { Project, ProjectMemberRole } from "../types";

const ROLES: ProjectMemberRole[] = ["lead", "member"];

export function ProjectMembers({ project }: { project: Project }) {
  const { role } = useAuth();
  const canManage = can(role, "project.manage");
  const archived = project.status === "archived";

  const query = useProjectMembers(project.id);
  const members = query.data ?? [];

  const addMember = useAddMember(project.id);
  const removeMember = useRemoveMember(project.id);
  const updateRole = useUpdateMemberRole(project.id);

  const [selectedEmployee, setSelectedEmployee] = React.useState("");
  const [selectedRole, setSelectedRole] = React.useState<ProjectMemberRole>("member");

  const employeesQuery = useEmployees({
    q: "",
    status: "active",
    department: "",
    manager_id: "",
    limit: 100,
    offset: 0,
  });
  const assignedIds = new Set(members.map((m) => m.employee_id));
  const available = (employeesQuery.data?.items ?? []).filter((e) => !assignedIds.has(e.id));

  async function assign() {
    if (!selectedEmployee) return;
    try {
      await addMember.mutateAsync({ employee_id: selectedEmployee, role: selectedRole });
      toast.success("Member assigned");
      setSelectedEmployee("");
      setSelectedRole("member");
    } catch (error) {
      toast.error(error instanceof AppError ? error.message : "Could not assign member.");
    }
  }

  async function changeRole(employeeId: string, next: ProjectMemberRole) {
    try {
      await updateRole.mutateAsync({ employeeId, role: next });
    } catch (error) {
      toast.error(error instanceof AppError ? error.message : "Could not update role.");
    }
  }

  async function remove(employeeId: string, name: string) {
    try {
      await removeMember.mutateAsync(employeeId);
      toast.success(`${name} removed`);
    } catch (error) {
      toast.error(error instanceof AppError ? error.message : "Could not remove member.");
    }
  }

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
              <li key={m.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                <span className="min-w-0 truncate font-medium">{m.employee_name}</span>
                {canManage ? (
                  <div className="flex items-center gap-2">
                    <Select
                      value={m.role}
                      onValueChange={(v) =>
                        void changeRole(m.employee_id, v as ProjectMemberRole)
                      }
                    >
                      <SelectTrigger className="h-8 w-28">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {ROLES.map((r) => (
                          <SelectItem key={r} value={r}>
                            {r}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Remove ${m.employee_name}`}
                      onClick={() => void remove(m.employee_id, m.employee_name)}
                    >
                      <UserMinus className="h-4 w-4" />
                    </Button>
                  </div>
                ) : (
                  <Badge variant={m.role === "lead" ? "info" : "neutral"}>{m.role}</Badge>
                )}
              </li>
            ))}
          </ul>
        )}

        {canManage && !archived && (
          <>
            <Separator className="my-4" />
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <Select value={selectedEmployee} onValueChange={setSelectedEmployee}>
                <SelectTrigger className="sm:flex-1">
                  <SelectValue placeholder="Add an employee…" />
                </SelectTrigger>
                <SelectContent>
                  {available.length === 0 ? (
                    <div className="px-2 py-1.5 text-sm text-muted-foreground">
                      No employees available
                    </div>
                  ) : (
                    available.map((e) => (
                      <SelectItem key={e.id} value={e.id}>
                        {e.full_name} · {e.employee_code}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
              <Select
                value={selectedRole}
                onValueChange={(v) => setSelectedRole(v as ProjectMemberRole)}
              >
                <SelectTrigger className="sm:w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROLES.map((r) => (
                    <SelectItem key={r} value={r}>
                      {r}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                onClick={() => void assign()}
                disabled={!selectedEmployee}
                loading={addMember.isPending}
              >
                Add
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
