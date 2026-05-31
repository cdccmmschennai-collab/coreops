import { api } from "@/lib/api-client";

import type {
  Employee,
  EmployeeCreateBody,
  EmployeeListParams,
  EmployeePage,
  EmployeeUpdateBody,
} from "./types";

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
};
