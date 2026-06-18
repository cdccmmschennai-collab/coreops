export const activityMasterKeys = {
  all: ["activity-master"] as const,
  activities: (activeOnly?: boolean) => [...activityMasterKeys.all, "activities", activeOnly] as const,
  subActivities: (activityId: string, activeOnly?: boolean) =>
    [...activityMasterKeys.all, "sub-activities", activityId, activeOnly] as const,
  flatSubActivities: (activeOnly?: boolean) =>
    [...activityMasterKeys.all, "sub-activities-flat", activeOnly] as const,
};
