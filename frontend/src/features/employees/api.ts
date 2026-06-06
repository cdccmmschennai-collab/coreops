import { api } from "@/lib/api-client";
import type { components } from "@/types/openapi";

import type {
  Employee,
  EmployeeCreateBody,
  EmployeeListParams,
  EmployeePage,
  EmployeeUpdateBody,
} from "./types";

export type UserOut = components["schemas"]["UserOut"];

export interface AccountCreateBody {
  email: string;
  password: string;
  role: "project_manager" | "employee";
}

export interface AccountPasswordResetBody {
  new_password: string;
}

export interface AccountStatusUpdateBody {
  is_active: boolean;
}

export interface AccountRoleUpdateBody {
  role: "project_manager" | "employee";
}

export interface AccountLinkBody {
  user_id: string;
}

function toQuery(p: EmployeeListParams): string {
  const sp = new URLSearchParams();
  if (p.q) sp.set("q", p.q);
  if (p.status) sp.set("status", p.status);
  if (p.department) sp.set("department", p.department);
  if (p.manager_id) sp.set("manager_id", p.manager_id);
  sp.set("limit", String(p.limit));
  sp.set("offset", String(p.offset));
  return sp.toString();
}

export const employeesApi = {
  list: (params: EmployeeListParams) =>
    api.get<EmployeePage>(`/employees?${toQuery(params)}`),
  get: (id: string) => api.get<Employee>(`/employees/${id}`),
  create: (body: EmployeeCreateBody) => api.post<Employee>("/employees", body),
  update: (id: string, body: EmployeeUpdateBody) =>
    api.patch<Employee>(`/employees/${id}`, body),
  deactivate: (id: string) => api.del<void>(`/employees/${id}`),
  getTeam: (id: string) => api.get<Employee[]>(`/employees/${id}/team`),

  // account management
  createAccount: (id: string, body: AccountCreateBody) =>
    api.post<UserOut>(`/employees/${id}/account`, body),
  resetAccountPassword: (id: string, body: AccountPasswordResetBody) =>
    api.patch<void>(`/employees/${id}/account/password`, body),
  updateAccountStatus: (id: string, body: AccountStatusUpdateBody) =>
    api.patch<UserOut>(`/employees/${id}/account/status`, body),
  changeAccountRole: (id: string, body: AccountRoleUpdateBody) =>
    api.patch<UserOut>(`/employees/${id}/account/role`, body),
  relinkAccount: (id: string, body: AccountLinkBody) =>
    api.patch<UserOut>(`/employees/${id}/account/link`, body),
  unlinkAccount: (id: string) => api.del<void>(`/employees/${id}/account/link`),
};
