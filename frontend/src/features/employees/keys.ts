import type { EmployeeListParams } from "./types";

export const employeesKeys = {
  all: ["employees"] as const,
  list: (params: EmployeeListParams) => ["employees", "list", params] as const,
  detail: (id: string) => ["employees", "detail", id] as const,
};
