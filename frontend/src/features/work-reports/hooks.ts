import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { workReportsApi } from "./api";
import { workReportKeys } from "./keys";
import type {
  WorkReportCreateBody,
  WorkReportEditRequestBody,
  WorkReportListParams,
  WorkReportRejectBody,
  WorkReportUpdateBody,
} from "./types";

export function useWorkReportList(params: WorkReportListParams) {
  return useQuery({
    queryKey: workReportKeys.list(params),
    queryFn: () => workReportsApi.list(params),
    placeholderData: (prev) => prev,
  });
}

export function useWorkReport(id: string | undefined, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: workReportKeys.detail(id ?? ""),
    queryFn: () => workReportsApi.get(id as string),
    enabled: (options?.enabled ?? true) && !!id,
  });
}

export function useCreateWorkReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: WorkReportCreateBody) => workReportsApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: workReportKeys.all }),
  });
}

export function useUpdateWorkReport(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: WorkReportUpdateBody) => workReportsApi.update(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: workReportKeys.all });
      qc.invalidateQueries({ queryKey: workReportKeys.detail(id) });
    },
  });
}

function useReportActionInvalidation(id: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: workReportKeys.all });
    qc.invalidateQueries({ queryKey: workReportKeys.detail(id) });
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

export function useRejectWorkReport(id: string) {
  const invalidate = useReportActionInvalidation(id);
  return useMutation({
    mutationFn: (body: WorkReportRejectBody) => workReportsApi.reject(id, body),
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
    onSuccess: () => qc.invalidateQueries({ queryKey: workReportKeys.all }),
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
