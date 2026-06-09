import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { tasksApi } from "./api";
import { tasksKeys } from "./keys";
import type {
  TaskCreateBody,
  TaskListParams,
  TaskStatusUpdateBody,
  TaskUpdateBody,
} from "./types";

export function useTasks(params: TaskListParams) {
  return useQuery({
    queryKey: tasksKeys.list(params),
    queryFn: () => tasksApi.list(params),
    placeholderData: (prev) => prev,
  });
}

export function useTask(id: string | undefined) {
  return useQuery({
    queryKey: tasksKeys.detail(id ?? ""),
    queryFn: () => tasksApi.get(id as string),
    enabled: !!id,
  });
}

export function useCreateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TaskCreateBody) => tasksApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: tasksKeys.all }),
  });
}

export function useUpdateTask(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TaskUpdateBody) => tasksApi.update(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: tasksKeys.all });
      qc.invalidateQueries({ queryKey: tasksKeys.detail(id) });
    },
  });
}

export function useUpdateTaskStatus(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TaskStatusUpdateBody) => tasksApi.updateStatus(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: tasksKeys.all });
      qc.invalidateQueries({ queryKey: tasksKeys.detail(id) });
    },
  });
}
