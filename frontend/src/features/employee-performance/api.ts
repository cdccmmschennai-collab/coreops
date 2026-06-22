import { api } from "@/lib/api-client";

import type {
  EmployeeBenchmarks,
  EmployeeOverview,
  EmployeesPerformancePage,
  PerformanceParams,
} from "./types";

function toQuery(p: PerformanceParams): string {
  const sp = new URLSearchParams();
  sp.set("page", String(p.page));
  sp.set("page_size", String(p.page_size));
  if (p.search) sp.set("search", p.search);
  sp.set("sort", p.sort);
  sp.set("order", p.order);
  return sp.toString();
}

export const performanceApi = {
  // Layer 1 — comparison list (search / sort / paginate).
  list: (params: PerformanceParams) =>
    api.get<EmployeesPerformancePage>(
      `/benchmarks/employees-performance?${toQuery(params)}`,
    ),
  // Layer 2/3 — shared overview aggregation.
  overview: (id: string) =>
    api.get<EmployeeOverview>(`/benchmarks/employees/${id}/overview`),
  // Layer 3 Benchmarks tab — full weekly ledger for client-side reconciliation.
  benchmarks: (id: string) =>
    api.get<EmployeeBenchmarks>(`/benchmarks/employees/${id}/benchmarks`),
};
