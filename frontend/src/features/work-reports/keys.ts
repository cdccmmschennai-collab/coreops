import type { WorkReportListParams } from "./types";

export const workReportKeys = {
  all: ["work-reports"] as const,
  list: (params: WorkReportListParams) => ["work-reports", "list", params] as const,
  detail: (id: string) => ["work-reports", "detail", id] as const,
  openTasks: (reportDate: string) => ["work-reports", "open-tasks", reportDate] as const,
};
