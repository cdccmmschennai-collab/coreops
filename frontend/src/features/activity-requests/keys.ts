export const activityRequestKeys = {
  all: ["activity-requests"] as const,
  list: (status: string) => ["activity-requests", "list", status] as const,
  mine: (reportId: string) => ["activity-requests", "mine", reportId] as const,
  pendingCount: () => ["activity-requests", "pending-count"] as const,
};
