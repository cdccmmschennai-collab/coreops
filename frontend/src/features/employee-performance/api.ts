import { api } from "@/lib/api-client";
import { getToken } from "@/lib/auth-storage";
import { env } from "@/lib/env";

import type {
  BenchmarkCycle,
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
  sp.set("cycle", p.cycle);
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

/**
 * Streams the Pending Benchmark .xlsx for the given cycle and triggers a
 * browser download, named from the response's Content-Disposition (the
 * backend embeds the cycle dates). Goes through fetch directly (not
 * api-client) because the response is a binary blob, not JSON — but still
 * attaches the bearer token.
 */
export async function downloadPendingBenchmarkXlsx(cycle: BenchmarkCycle): Promise<void> {
  const res = await fetch(`${env.apiBaseUrl}/benchmarks/pending-export.xlsx?cycle=${cycle}`, {
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Export failed (${res.status})`);
  const disposition = res.headers.get("content-disposition") ?? "";
  const filename =
    /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? "pending-benchmark.xlsx";
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
