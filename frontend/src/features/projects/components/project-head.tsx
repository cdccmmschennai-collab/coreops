"use client";

import * as React from "react";
import { X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useActivities } from "@/features/activity-master/hooks";
import type { ActivityMaster } from "@/features/activity-master/types";
import { useAuth } from "@/features/auth/auth-provider";
import { useEmployees } from "@/features/employees/hooks";
import { AppError } from "@/lib/api-client";

import {
  useActivityStaffing,
  useAssignActivityMember,
  useRemoveActivityMember,
} from "../hooks";
import {
  type ActivityMember,
  type ActivityMemberRole,
  type ActivityStaffing,
  type Project,
} from "../types";
import { ProjectRoleBadges, type ProjectRoleKey } from "./project-role-badges";

/** Minimal shape of an employee option in the assign dropdown. */
type EmployeeOption = { id: string; full_name: string; employee_code: string };

/** Base role plus, additively, the QC badge when the person also holds QC. */
function assignmentRoles(member: ActivityMember): { role: ProjectRoleKey }[] {
  const roles: { role: ProjectRoleKey }[] = [{ role: member.role }];
  if (member.is_qc) roles.push({ role: "qc" });
  return roles;
}

/**
 * Head-only activity staffing surface (Phase 3). Rendered only when the logged-in
 * user IS the project's Head. Cards are generated from the activity master (never
 * hardcoded); each card lists its current staffing and lets the Head assign a
 * member (employee + role + optional QC) or unassign one via the real
 * /projects/{id}/activity-staffing endpoints.
 */
export function ProjectHeadActivities({ project }: { project: Project }) {
  const { employeeId } = useAuth();
  const isHead = !!employeeId && employeeId === project.head_employee_id;

  const activitiesQuery = useActivities(true);
  const activities = (activitiesQuery.data ?? []).filter((a) => a.level === "activity");

  const staffingQuery = useActivityStaffing(isHead ? project.id : undefined);
  const staffingByActivity = React.useMemo(() => {
    const map = new Map<string, ActivityStaffing>();
    for (const s of staffingQuery.data ?? []) map.set(s.activity_id, s);
    return map;
  }, [staffingQuery.data]);

  // Any active employee can be staffed onto an activity.
  const employeesQuery = useEmployees({
    q: "",
    status: "active",
    department: "",
    manager_id: "",
    limit: 100,
    offset: 0,
  });
  const employees = (employeesQuery.data?.items ?? []) as EmployeeOption[];

  if (!isHead) return null;

  const archived = project.status === "archived";

  return (
    <Card className="md:col-span-2">
      <CardHeader>
        <CardTitle>Activities</CardTitle>
      </CardHeader>
      <CardContent>
        {activitiesQuery.isLoading ? (
          <p className="text-sm text-muted-foreground">Loading activities…</p>
        ) : activities.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No activities defined in the activity master.
          </p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {activities.map((activity) => (
              <ActivityManageCard
                key={activity.id}
                projectId={project.id}
                activity={activity}
                staffing={staffingByActivity.get(activity.id)}
                employees={employees}
                disabled={archived}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ActivityManageCard({
  projectId,
  activity,
  staffing,
  employees,
  disabled,
}: {
  projectId: string;
  activity: ActivityMaster;
  staffing: ActivityStaffing | undefined;
  employees: EmployeeOption[];
  disabled: boolean;
}) {
  const assign = useAssignActivityMember(projectId);
  const remove = useRemoveActivityMember(projectId);

  // Lead first, then contributors — the same order the read view uses.
  const assignments: ActivityMember[] = React.useMemo(() => {
    if (!staffing) return [];
    return [staffing.lead, ...(staffing.contributors ?? [])].filter(
      (m): m is ActivityMember => !!m,
    );
  }, [staffing]);

  const assignedIds = new Set(assignments.map((a) => a.employee_id));
  const available = employees.filter((e) => !assignedIds.has(e.id));
  const hasLead = !!staffing?.lead;

  const [employee, setEmployee] = React.useState("");
  const [role, setRole] = React.useState<ActivityMemberRole>("contributor");
  const [isQc, setIsQc] = React.useState(false);

  async function add() {
    if (!employee) return;
    try {
      await assign.mutateAsync({
        activityId: activity.id,
        body: { employee_id: employee, role, is_qc: isQc },
      });
      toast.success("Member assigned");
      setEmployee("");
      setRole("contributor");
      setIsQc(false);
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not assign member.");
    }
  }

  async function unassign(employeeId: string) {
    try {
      await remove.mutateAsync({ activityId: activity.id, employeeId });
      toast.success("Member removed");
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not remove member.");
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{activity.code ?? activity.name}</CardTitle>
        {activity.code && activity.name !== activity.code && (
          <p className="text-xs text-muted-foreground">{activity.name}</p>
        )}
      </CardHeader>
      <CardContent>
        {assignments.length === 0 ? (
          <p className="text-sm text-muted-foreground">No one assigned yet.</p>
        ) : (
          <ul className="divide-y divide-border">
            {assignments.map((a) => (
              <li
                key={a.id}
                className="flex items-start justify-between gap-2 py-2 text-sm"
              >
                <div className="min-w-0">
                  <div className="truncate font-medium">{a.employee_name}</div>
                  <ProjectRoleBadges roles={assignmentRoles(a)} />
                </div>
                {!disabled && (
                  <button
                    type="button"
                    title="Remove from activity"
                    onClick={() => void unassign(a.employee_id)}
                    className="mt-0.5 flex-shrink-0 rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}

        {!disabled && (
          <div className="mt-3 space-y-2 border-t border-border pt-3">
            <Select value={employee} onValueChange={setEmployee}>
              <SelectTrigger>
                <SelectValue placeholder="Add member…" />
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
            <div className="flex items-center gap-2">
              <Select
                value={role}
                onValueChange={(v) => setRole(v as ActivityMemberRole)}
              >
                <SelectTrigger className="flex-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="lead" disabled={hasLead}>
                    Lead
                  </SelectItem>
                  <SelectItem value="contributor">Contributor</SelectItem>
                </SelectContent>
              </Select>
              <label className="flex items-center gap-1.5 whitespace-nowrap text-sm text-muted-foreground">
                <Checkbox
                  checked={isQc}
                  onChange={(e) => setIsQc(e.target.checked)}
                />
                QC
              </label>
              <Button
                size="sm"
                onClick={() => void add()}
                disabled={!employee}
                loading={assign.isPending}
              >
                Add
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
