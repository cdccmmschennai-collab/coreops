export const benchmarksKeys = {
  all:      ["benchmarks"] as const,
  myAlerts: () => [...benchmarksKeys.all, "my-alerts"] as const,
};
