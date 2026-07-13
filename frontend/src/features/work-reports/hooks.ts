import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { complianceKeys } from "@/features/report-compliance/hooks";

import { workReportsApi } from "./api";
import { workReportKeys } from "./keys";
import type {
  WorkReportCreateBody,
  WorkReportEditRequestBody,
  WorkReportListParams,
  WorkReportUpdateBody,
} from "./types";

export function useWorkReportList(
  params: WorkReportListParams,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: workReportKeys.list(params),
    queryFn: () => workReportsApi.list(params),
    placeholderData: (prev) => prev,
    enabled: options?.enabled ?? true,
  });
}

export function useWorkReport(id: string | undefined, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: workReportKeys.detail(id ?? ""),
    queryFn: () => workReportsApi.get(id as string),
    enabled: (options?.enabled ?? true) && !!id,
  });
}

/** Open (unfinished) work items the current employee can continue in a report
 * dated `reportDate`. Feature-flagged; callers pass enabled=false when the
 * task-continuation feature is off or no date is chosen yet. */
export function useOpenTasks(reportDate: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: workReportKeys.openTasks(reportDate),
    queryFn: () => workReportsApi.openTasks(reportDate),
    enabled: (options?.enabled ?? true) && !!reportDate,
  });
}

export function useCreateWorkReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: WorkReportCreateBody) => workReportsApi.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: workReportKeys.all });
      // A create may submit today's report — refresh the compliance snapshot so
      // the 5:15 reminder and logout guard see it immediately.
      qc.invalidateQueries({ queryKey: complianceKeys.me() });
    },
  });
}

export function useUpdateWorkReport(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: WorkReportUpdateBody) => workReportsApi.update(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: workReportKeys.all });
      qc.invalidateQueries({ queryKey: workReportKeys.detail(id) });
      qc.invalidateQueries({ queryKey: complianceKeys.me() });
    },
  });
}

function useReportActionInvalidation(id: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: workReportKeys.all });
    qc.invalidateQueries({ queryKey: workReportKeys.detail(id) });
    // Submit / delete / status changes affect today's compliance state.
    qc.invalidateQueries({ queryKey: complianceKeys.me() });
  };
}

export function useSubmitWorkReport(id: string) {
  const invalidate = useReportActionInvalidation(id);
  return useMutation({
    mutationFn: () => workReportsApi.submit(id),
    onSuccess: invalidate,
  });
}

export function useRequestEditWorkReport(id: string) {
  const invalidate = useReportActionInvalidation(id);
  return useMutation({
    mutationFn: (body: WorkReportEditRequestBody) => workReportsApi.requestEdit(id, body),
    onSuccess: invalidate,
  });
}

export function useGrantEditWorkReport(id: string) {
  const invalidate = useReportActionInvalidation(id);
  return useMutation({
    mutationFn: () => workReportsApi.grantEdit(id),
    onSuccess: invalidate,
  });
}

export function useDeleteWorkReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => workReportsApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: workReportKeys.all });
      qc.invalidateQueries({ queryKey: complianceKeys.me() });
    },
  });
}

/** Toggle a TASK_BASED row's completion checkbox. `reportId` is only used to
 * invalidate that report's detail query — the mutation itself targets the
 * task row directly and works regardless of the parent report's status. */
export function useToggleTaskCompletion(reportId: string) {
  const invalidate = useReportActionInvalidation(reportId);
  return useMutation({
    mutationFn: ({ taskId, isCompleted }: { taskId: string; isCompleted: boolean }) =>
      workReportsApi.toggleTaskCompletion(taskId, { is_completed: isCompleted }),
    onSuccess: invalidate,
  });
}
