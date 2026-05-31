import type { components } from "@/types/openapi";

// Types come straight from the live API contract (openapi-typescript output).
export type Employee = components["schemas"]["EmployeeOut"];
export type EmployeeStatus = components["schemas"]["EmployeeStatus"];
export type EmployeePage = components["schemas"]["EmployeePage"];
export type EmployeeCreateBody = components["schemas"]["EmployeeCreate"];
export type EmployeeUpdateBody = components["schemas"]["EmployeeUpdate"];

export interface EmployeeListParams {
  q: string;
  status: EmployeeStatus | "";
  department: string;
  manager_id: string;
  limit: number;
  offset: number;
}
