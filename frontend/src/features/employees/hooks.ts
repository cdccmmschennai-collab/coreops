import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  employeesApi,
  type AccountCreateBody,
  type AccountLinkBody,
  type AccountPasswordResetBody,
  type AccountRoleUpdateBody,
  type AccountStatusUpdateBody,
} from "./api";
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

export function useEmployeeTeam(id: string | undefined) {
  return useQuery({
    queryKey: ["employees", "detail", id ?? "", "team"],
    queryFn: () => employeesApi.getTeam(id as string),
    enabled: !!id,
  });
}

export function useCreateEmployeeAccount(empId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AccountCreateBody) => employeesApi.createAccount(empId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: employeesKeys.detail(empId) });
      qc.invalidateQueries({ queryKey: ["users"] });
    },
  });
}

export function useResetEmployeeAccountPassword(empId: string) {
  return useMutation({
    mutationFn: (body: AccountPasswordResetBody) =>
      employeesApi.resetAccountPassword(empId, body),
  });
}

export function useUpdateEmployeeAccountStatus(empId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AccountStatusUpdateBody) =>
      employeesApi.updateAccountStatus(empId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useChangeEmployeeAccountRole(empId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AccountRoleUpdateBody) =>
      employeesApi.changeAccountRole(empId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: employeesKeys.detail(empId) });
      qc.invalidateQueries({ queryKey: ["users"] });
    },
  });
}

export function useRelinkEmployeeAccount(empId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AccountLinkBody) => employeesApi.relinkAccount(empId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: employeesKeys.detail(empId) });
      qc.invalidateQueries({ queryKey: ["users"] });
    },
  });
}

export function useUnlinkEmployeeAccount(empId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => employeesApi.unlinkAccount(empId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: employeesKeys.detail(empId) });
      qc.invalidateQueries({ queryKey: ["users"] });
    },
  });
}
