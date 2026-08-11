import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { projectsApi } from "./api";
import { projectsKeys } from "./keys";
import type { WeeklyReportCycle } from "./weekly-report";
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
  TagScopeUpdateBody,
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

// ---------- tag scope ----------
/**
 * Current tag scope + revision history. The endpoint is PM/Head-only, so this
 * is gated on `enabled` (the caller passes the same authority the tab uses)
 * rather than firing a request every viewer would get a 403 for.
 */
export function useTagScope(id: string | undefined, enabled = true) {
  return useQuery({
    queryKey: projectsKeys.tagScope(id ?? ""),
    queryFn: () => projectsApi.getTagScope(id as string),
    enabled: !!id && enabled,
  });
}

/**
 * Establish or revise the scope. The response already carries the new current
 * scope and the full history, so it is written straight into the tag-scope
 * cache — the tab shows the new revision without waiting for a refetch. The
 * project detail is invalidated too because `projects.estimated_tag_count` /
 * `tag_scope_*` are denormalised onto the project row the Overview reads.
 */
export function useUpdateTagScope(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TagScopeUpdateBody) => projectsApi.updateTagScope(id, body),
    onSuccess: (scope) => {
      qc.setQueryData(projectsKeys.tagScope(id), scope);
      qc.invalidateQueries({ queryKey: projectsKeys.tagScope(id) });
      qc.invalidateQueries({ queryKey: projectsKeys.detail(id) });
      // Changing the estimate changes every activity's remaining figure.
      qc.invalidateQueries({ queryKey: projectsKeys.summary(id) });
      qc.invalidateQueries({ queryKey: projectsKeys.all });
    },
    onError: () => {
      // A 409 means our view of the revision is stale; pull the winning state
      // back so the reopened form starts from what is actually stored.
      qc.invalidateQueries({ queryKey: projectsKeys.tagScope(id) });
      qc.invalidateQueries({ queryKey: projectsKeys.detail(id) });
    },
  });
}

/** Summary tab data. Open to every project viewer, so no authority gate here. */
export function useProjectSummary(id: string | undefined) {
  return useQuery({
    queryKey: projectsKeys.summary(id ?? ""),
    queryFn: () => projectsApi.getSummary(id as string),
    enabled: !!id,
  });
}

/**
 * Weekly Report for one project and one cycle.
 *
 * `enabled` carries the caller's Head authority: the endpoint is Head-only, so
 * a non-Head must not fire a request that is guaranteed to come back 403 (the
 * tab is not rendered for them either way).
 *
 * `placeholderData` is deliberately NOT used here. Switching Current <-> Previous
 * must show a loading state rather than last week's rows sitting under this
 * week's heading - a stale row here is a wrong operational report, not a
 * cosmetic flicker.
 */
export function useProjectWeeklyReport(
  id: string | undefined,
  cycle: WeeklyReportCycle,
  enabled = true,
) {
  return useQuery({
    queryKey: projectsKeys.weeklyReport(id ?? "", cycle),
    queryFn: () => projectsApi.getWeeklyReport(id as string, cycle),
    enabled: !!id && enabled,
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
