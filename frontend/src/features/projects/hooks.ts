import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { projectsApi } from "./api";
import { projectsKeys } from "./keys";
import type {
  ActivityMemberCreateBody,
  ActivityMemberUpdateBody,
  PlannedDateUpdateBody,
  ProjectCreateBody,
  ProjectHeadUpdateBody,
  ProjectListParams,
  ProjectMemberCreateBody,
  ProjectMemberRole,
  ProjectUpdateBody,
} from "./types";

export function useProjects(params: ProjectListParams) {
  return useQuery({
    queryKey: projectsKeys.list(params),
    queryFn: () => projectsApi.list(params),
    placeholderData: (prev) => prev,
  });
}

export function useProject(id: string | undefined, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: projectsKeys.detail(id ?? ""),
    queryFn: () => projectsApi.get(id as string),
    enabled: (options?.enabled ?? true) && !!id,
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectCreateBody) => projectsApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: projectsKeys.all }),
  });
}

export function useUpdateProject(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectUpdateBody) => projectsApi.update(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: projectsKeys.all });
      qc.invalidateQueries({ queryKey: projectsKeys.detail(id) });
    },
  });
}

export function useArchiveProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => projectsApi.archive(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: projectsKeys.all }),
  });
}

export function useSetProjectHead(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectHeadUpdateBody) => projectsApi.setHead(id, body),
    onSuccess: () => {
      // Head assignment emits a timeline event and auto-adds a member row.
      qc.invalidateQueries({ queryKey: projectsKeys.detail(id) });
      qc.invalidateQueries({ queryKey: projectsKeys.timeline(id) });
      qc.invalidateQueries({ queryKey: projectsKeys.members(id) });
      qc.invalidateQueries({ queryKey: projectsKeys.all });
    },
  });
}

export function useUpdatePlannedDate(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PlannedDateUpdateBody) => projectsApi.updatePlannedDate(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: projectsKeys.detail(id) });
      qc.invalidateQueries({ queryKey: projectsKeys.plannedDateChanges(id) });
      qc.invalidateQueries({ queryKey: projectsKeys.all });
    },
  });
}

export function usePlannedDateChanges(id: string | undefined) {
  return useQuery({
    queryKey: projectsKeys.plannedDateChanges(id ?? ""),
    queryFn: () => projectsApi.listPlannedDateChanges(id as string),
    enabled: !!id,
  });
}

export function useProjectTimeline(id: string | undefined) {
  return useQuery({
    queryKey: projectsKeys.timeline(id ?? ""),
    queryFn: () => projectsApi.listTimeline(id as string),
    enabled: !!id,
  });
}

// ---------- membership ----------
export function useProjectMembers(id: string | undefined) {
  return useQuery({
    queryKey: projectsKeys.members(id ?? ""),
    queryFn: () => projectsApi.listMembers(id as string),
    enabled: !!id,
  });
}

function useMemberInvalidation(projectId: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: projectsKeys.members(projectId) });
    qc.invalidateQueries({ queryKey: projectsKeys.detail(projectId) });
    qc.invalidateQueries({ queryKey: projectsKeys.all });
  };
}

export function useAddMember(projectId: string) {
  const invalidate = useMemberInvalidation(projectId);
  return useMutation({
    mutationFn: (body: ProjectMemberCreateBody) => projectsApi.addMember(projectId, body),
    onSuccess: invalidate,
  });
}

export function useUpdateMemberRole(projectId: string) {
  const invalidate = useMemberInvalidation(projectId);
  return useMutation({
    mutationFn: (vars: { employeeId: string; role: ProjectMemberRole }) =>
      projectsApi.updateMemberRole(projectId, vars.employeeId, vars.role),
    onSuccess: invalidate,
  });
}

export function useRemoveMember(projectId: string) {
  const invalidate = useMemberInvalidation(projectId);
  return useMutation({
    mutationFn: (employeeId: string) => projectsApi.removeMember(projectId, employeeId),
    onSuccess: invalidate,
  });
}

// ---------- activity staffing (Phase 3) ----------
export function useActivityStaffing(id: string | undefined) {
  return useQuery({
    queryKey: projectsKeys.activityStaffing(id ?? ""),
    queryFn: () => projectsApi.listActivityStaffing(id as string),
    enabled: !!id,
  });
}

/** Active employees that may be staffed onto an activity (the shared assignment
 * form's Employee options). Restricted to staffing managers server-side, so it
 * only fetches for authorized viewers. */
export function useAssignableEmployees(id: string, enabled: boolean) {
  return useQuery({
    queryKey: projectsKeys.assignableEmployees(id),
    queryFn: () => projectsApi.listAssignableEmployees(id),
    enabled: !!id && enabled,
  });
}

/** Staffing changes also touch the visibility backbone (project_members) and the
 * member_count on the project, so invalidate those alongside the staffing list. */
function useActivityStaffingInvalidation(projectId: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: projectsKeys.activityStaffing(projectId) });
    qc.invalidateQueries({ queryKey: projectsKeys.members(projectId) });
    qc.invalidateQueries({ queryKey: projectsKeys.detail(projectId) });
    qc.invalidateQueries({ queryKey: projectsKeys.all });
  };
}

export function useAssignActivityMember(projectId: string) {
  const invalidate = useActivityStaffingInvalidation(projectId);
  return useMutation({
    mutationFn: (vars: { activityId: string; body: ActivityMemberCreateBody }) =>
      projectsApi.assignActivityMember(projectId, vars.activityId, vars.body),
    onSuccess: invalidate,
  });
}

export function useUpdateActivityMember(projectId: string) {
  const invalidate = useActivityStaffingInvalidation(projectId);
  return useMutation({
    mutationFn: (vars: {
      activityId: string;
      employeeId: string;
      body: ActivityMemberUpdateBody;
    }) =>
      projectsApi.updateActivityMember(
        projectId,
        vars.activityId,
        vars.employeeId,
        vars.body,
      ),
    onSuccess: invalidate,
  });
}

export function useRemoveActivityMember(projectId: string) {
  const invalidate = useActivityStaffingInvalidation(projectId);
  return useMutation({
    mutationFn: (vars: { activityId: string; employeeId: string }) =>
      projectsApi.removeActivityMember(projectId, vars.activityId, vars.employeeId),
    onSuccess: invalidate,
  });
}
