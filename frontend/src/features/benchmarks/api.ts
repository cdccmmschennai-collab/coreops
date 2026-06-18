import { api } from "@/lib/api-client";

import type { MyAlerts } from "./types";

export const benchmarksApi = {
  myAlerts: () => api.get<MyAlerts>("/benchmarks/my-alerts"),
};
