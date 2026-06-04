export const jobCodeKeys = {
  all: ["job-codes"] as const,
  list: (params?: object) => [...jobCodeKeys.all, "list", params] as const,
};
