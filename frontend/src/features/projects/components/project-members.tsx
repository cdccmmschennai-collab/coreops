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
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { useActivities } from "@/features/activity-master/hooks";
import type { ActivityMaster } from "@/features/activity-master/types";
import { useAuth } from "@/features/auth/auth-provider";
import { useEmployees } from "@/features/employees/hooks";
import { AppError } from "@/lib/api-client";
import { can } from "@/lib/rbac";

import {
  useActivityStaffing,
  useAssignActivityMember,
  useAssignableEmployees,
  useRemoveActivityMember,
  useSetProjectHead,
} from "../hooks";
import {
  type ActivityMember,
  type ActivityMemberRole,
  type ActivityStaffing,
  type Project,
} from "../types";
import { ProjectRoleBadges, type ProjectRoleKey } from "./project-role-badges";

/** Attendance/admin activity names that live in the work-report Day Status
 * dropdown, not the project-execution pickers — matches the backend's canonical
 * set in scripts/deactivate_attendance_activities.py. Excluded from the shared
 * assignment form's Activity dropdown so only benchmark activities are staffable. */
const ATTENDANCE_ACTIVITY_NAMES = new Set([
  "LEAVE",
  "COMPANY HOLIDAY",
  "WORK FROM HOME",
  "WEEK OFF",
  "WORK AT OFFICE",
  "COMP-OFF",
  "OVERTIME HOURS-COMPENSATION",
  "OVERTIME HOURS-SALARY",
  "PERMISSION",
]);

function isProjectExecutionActivity(a: ActivityMaster): boolean {
  if (a.level !== "activity") return false;
  const name = a.name.trim().toUpperCase();
  if (ATTENDANCE_ACTIVITY_NAMES.has(name)) return false;
  if (name.startsWith("OVERTIME")) return false;
  return true;
}

/** The effective role badges for one activity assignment: the base role plus,
 * additively, the QC badge when the person also holds QC. */
function assignmentRoles(member: ActivityMember): { role: ProjectRoleKey }[] {
  const roles: { role: ProjectRoleKey }[] = [{ role: member.role }];
  if (member.is_qc) roles.push({ role: "qc" });
  return roles;
}

function AssignmentRow({
  member,
  onRemove,
  isLead = false,
}: {
  member: ActivityMember;
  onRemove?: () => void;
  isLead?: boolean;
}) {
  return (
    <li className="flex items-center justify-between gap-2 py-2 text-sm">
      <span
        className={`min-w-0 truncate ${isLead ? "font-medium" : "font-normal"}`}
      >
        {member.employee_name}
      </span>
      <div className="flex flex-shrink-0 items-center gap-1.5">
        <ProjectRoleBadges
          roles={assignmentRoles(member)}
          className="flex flex-wrap items-center justify-end gap-1.5"
        />
        {onRemove && (
          <button
            type="button"
            title="Remove from activity"
            onClick={onRemove}
            className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </li>
  );
}

/** One shared form for the whole project: pick an employee, an activity, a role
 * and optional QC, then assign via the existing activity-staffing API. Replaces
 * the per-activity Add-member forms. Rendered only for staffing managers. */
function AssignActivityForm({
  projectId,
  staffing,
}: {
  projectId: string;
  staffing: ActivityStaffing[];
}) {
  const assign = useAssignActivityMember(projectId);
  const employeesQuery = useAssignableEmployees(projectId, true);
  const activitiesQuery = useActivities(true);

  const employees = employeesQuery.data ?? [];
  const activities = React.useMemo(
    () => (activitiesQuery.data ?? []).filter(isProjectExecutionActivity),
    [activitiesQuery.data],
  );

  // Activities that already have a Lead — the one-Lead-per-activity rule is
  // enforced server-side; disabling the option here avoids the 409 round-trip.
  const leadActivityIds = React.useMemo(
    () => new Set(staffing.filter((s) => s.lead).map((s) => s.activity_id)),
    [staffing],
  );

  const [employee, setEmployee] = React.useState("");
  const [activity, setActivity] = React.useState("");
  const [role, setRole] = React.useState<ActivityMemberRole>("contributor");
  const [isQc, setIsQc] = React.useState(false);

  const selectedHasLead = !!activity && leadActivityIds.has(activity);

  async function add() {
    if (!employee || !activity) return;
    try {
      await assign.mutateAsync({
        activityId: activity,
        body: { employee_id: employee, role, is_qc: isQc },
      });
      toast.success("Assignment added");
      setEmployee("");
      setActivity("");
      setRole("contributor");
      setIsQc(false);
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not add assignment.");
    }
  }

  return (
    <>
      <Separator className="my-4" />
      <p className="mb-2 text-sm font-medium">Assign Employee</p>
      <div className="space-y-2">
        <Select value={employee} onValueChange={setEmployee}>
          <SelectTrigger>
            <SelectValue placeholder="Select employee…" />
          </SelectTrigger>
          <SelectContent>
            {employees.length === 0 ? (
              <div className="px-2 py-1.5 text-sm text-muted-foreground">
                No employees available
              </div>
            ) : (
              employees.map((e) => (
                <SelectItem key={e.id} value={e.id}>
                  {e.full_name} · {e.employee_code}
                </SelectItem>
              ))
            )}
          </SelectContent>
        </Select>

        <Select
          value={activity}
          onValueChange={(v) => {
            setActivity(v);
            // Can't add a second Lead — fall back to Contributor.
            if (role === "lead" && leadActivityIds.has(v)) setRole("contributor");
          }}
        >
          <SelectTrigger>
            <SelectValue placeholder="Select activity…" />
          </SelectTrigger>
          <SelectContent>
            {activities.length === 0 ? (
              <div className="px-2 py-1.5 text-sm text-muted-foreground">
                No activities available
              </div>
            ) : (
              activities.map((a) => (
                <SelectItem key={a.id} value={a.id}>
                  {a.code ?? a.name}
                </SelectItem>
              ))
            )}
          </SelectContent>
        </Select>

        <div className="flex items-center gap-2">
          <Select value={role} onValueChange={(v) => setRole(v as ActivityMemberRole)}>
            <SelectTrigger className="flex-1">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="lead" disabled={selectedHasLead}>
                Lead
              </SelectItem>
              <SelectItem value="contributor">Contributor</SelectItem>
            </SelectContent>
          </Select>
          <label className="flex items-center gap-1.5 whitespace-nowrap text-sm text-muted-foreground">
            <Checkbox checked={isQc} onChange={(e) => setIsQc(e.target.checked)} />
            QC
          </label>
          <Button
            onClick={() => void add()}
            disabled={!employee || !activity}
            loading={assign.isPending}
          >
            Add Assignment
          </Button>
        </div>
      </div>
    </>
  );
}

export function ProjectMembers({ project }: { project: Project }) {
  const { role, employeeId } = useAuth();
  const canManage = can(role, "project.manage");
  const archived = project.status === "archived";
  const headEmployeeId = project.head_employee_id;

  // PM (any project) or the project's Head may modify activity staffing — the
  // same authority the backend enforces on assign/remove.
  const isHead = !!employeeId && employeeId === headEmployeeId;
  const canModifyStaffing = (canManage || isHead) && !archived;

  const staffingQuery = useActivityStaffing(project.id);
  // Only activities with assignments come back — render each as its own section.
  const staffing = staffingQuery.data ?? [];

  const setHead = useSetProjectHead(project.id);
  const removeMember = useRemoveActivityMember(project.id);
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

  async function unassign(activityId: string, employeeId: string) {
    try {
      await removeMember.mutateAsync({ activityId, employeeId });
      toast.success("Member removed");
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not remove member.");
    }
  }

  const hasHead = !!headEmployeeId && !!project.head_employee_name;
  const isEmpty = !hasHead && staffing.length === 0;

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
          <div className="space-y-2">
            {/* Project Head — single amber row, pinned to the top. */}
            {hasHead && (
              <div className="flex items-center justify-between gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm">
                <span className="min-w-0 truncate font-semibold">
                  {project.head_employee_name}
                </span>
                <ProjectRoleBadges
                  roles={[{ role: "head" }]}
                  className="flex flex-shrink-0 items-center gap-1.5"
                />
              </div>
            )}

            {/* One full-width bordered box per assigned activity (Lead first,
                then Contributors), already ordered by the activity master
                sort_order server-side. */}
            {staffing.map((activity) => (
              <div
                key={activity.activity_id}
                className="rounded-md border border-border px-3 py-2.5"
              >
                <p className="mb-1 text-sm font-semibold uppercase tracking-wide text-blue-700">
                  {activity.activity_code ?? activity.activity_name}
                </p>
                <ul className="divide-y divide-border">
                  {activity.lead && (
                    <AssignmentRow
                      key={activity.lead.id}
                      member={activity.lead}
                      isLead
                      onRemove={
                        canModifyStaffing
                          ? () =>
                              void unassign(
                                activity.activity_id,
                                activity.lead!.employee_id,
                              )
                          : undefined
                      }
                    />
                  )}
                  {(activity.contributors ?? []).map((c) => (
                    <AssignmentRow
                      key={c.id}
                      member={c}
                      onRemove={
                        canModifyStaffing
                          ? () => void unassign(activity.activity_id, c.employee_id)
                          : undefined
                      }
                    />
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}

        {/* PM only assigns / changes the Project Head. Lead / Contributor / QC
            are activity-level, assigned via the shared form below. */}
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

        {/* Shared activity-staffing form — PM or Head, active projects only. */}
        {canModifyStaffing && (
          <AssignActivityForm projectId={project.id} staffing={staffing} />
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
