import type { PerformanceParams } from "./types";

export const performanceKeys = {
  all: ["employee-performance"] as const,
  list: (params: PerformanceParams) =>
    [...performanceKeys.all, "list", params] as const,
  overview: (id: string) => [...performanceKeys.all, "overview", id] as const,
  benchmarks: (id: string) => [...performanceKeys.all, "benchmarks", id] as const,
};
