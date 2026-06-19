import { api } from "@/lib/api-client";

import type { MyAlerts, TeamAlerts } from "./types";

export const benchmarksApi = {
  myAlerts: () => api.get<MyAlerts>("/benchmarks/my-alerts"),
  teamAlerts: () => api.get<TeamAlerts>("/benchmarks/team-alerts"),
};
