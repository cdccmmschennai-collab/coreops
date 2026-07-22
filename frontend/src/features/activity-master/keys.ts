export const activityMasterKeys = {
  all: ["activity-master"] as const,
  activities: (activeOnly?: boolean) => [...activityMasterKeys.all, "activities", activeOnly] as const,
  subActivities: (activityId: string, activeOnly?: boolean) =>
    [...activityMasterKeys.all, "sub-activities", activityId, activeOnly] as const,
  flatSubActivities: (activeOnly?: boolean) =>
    [...activityMasterKeys.all, "sub-activities-flat", activeOnly] as const,
  // Benchmark Guide read-only view. Deliberately a descendant of `all` so every
  // Activity Master mutation (which invalidates `all`) also refreshes the guide.
  // `scope` is a permission discriminator (role + employee) so one browser
  // session never serves another identity's access-filtered rows from cache.
  benchmarkGuide: (scope: string) =>
    [...activityMasterKeys.all, "benchmark-guide", scope] as const,
};
