import type { components } from "@/types/openapi";

// Types come straight from the live API contract (openapi-typescript output),
// extended with office_id added in migration 0008.
export type Employee = components["schemas"]["EmployeeOut"] & {
  office_id?: string | null;
};
export type EmployeeStatus = components["schemas"]["EmployeeStatus"];
export type EmployeePage = components["schemas"]["EmployeePage"];
export type EmployeeCreateBody = components["schemas"]["EmployeeCreate"] & {
  office_id?: string | null;
};
export type EmployeeUpdateBody = components["schemas"]["EmployeeUpdate"] & {
  office_id?: string | null;
};

export interface EmployeeListParams {
  q: string;
  status: EmployeeStatus | "";
  department: string;
  manager_id: string;
  limit: number;
  offset: number;
}
