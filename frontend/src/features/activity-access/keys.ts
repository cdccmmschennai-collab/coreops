export const activityAccessKeys = {
  all: ["activity-access"] as const,
  config: (activityId: string, limit: number, offset: number) =>
    [...activityAccessKeys.all, "config", activityId, limit, offset] as const,
  // Employee grant-picker search, scoped to the activity (results exclude
  // already-granted employees).
  search: (activityId: string, q: string) =>
    [...activityAccessKeys.all, "search", activityId, q] as const,
};
