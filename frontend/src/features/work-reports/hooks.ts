import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { workReportsApi } from "./api";
import { workReportKeys } from "./keys";
import type {
  WorkReportCreateBody,
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

export function useApproveWorkReport(id: string) {
  const invalidate = useReportActionInvalidation(id);
  return useMutation({
    mutationFn: () => workReportsApi.approve(id),
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

export function useDeleteWorkReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => workReportsApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: workReportKeys.all }),
  });
}
