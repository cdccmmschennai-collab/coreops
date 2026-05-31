import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { employeesApi } from "./api";
import { employeesKeys } from "./keys";
import type {
  EmployeeCreateBody,
  EmployeeListParams,
  EmployeeUpdateBody,
} from "./types";

export function useEmployees(params: EmployeeListParams) {
  return useQuery({
    queryKey: employeesKeys.list(params),
    queryFn: () => employeesApi.list(params),
    placeholderData: (prev) => prev, // keep previous page while paginating/filtering
  });
}

export function useEmployee(id: string | undefined, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: employeesKeys.detail(id ?? ""),
    queryFn: () => employeesApi.get(id as string),
    enabled: (options?.enabled ?? true) && !!id,
  });
}

export function useCreateEmployee() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: EmployeeCreateBody) => employeesApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: employeesKeys.all }),
  });
}

export function useUpdateEmployee(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: EmployeeUpdateBody) => employeesApi.update(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: employeesKeys.all });
      qc.invalidateQueries({ queryKey: employeesKeys.detail(id) });
    },
  });
}

export function useDeactivateEmployee() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => employeesApi.deactivate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: employeesKeys.all }),
  });
}
