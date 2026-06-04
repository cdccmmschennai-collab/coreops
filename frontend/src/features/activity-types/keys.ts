export const activityTypeKeys = {
  all: ["activity-types"] as const,
  list: (params?: object) => [...activityTypeKeys.all, "list", params] as const,
};
