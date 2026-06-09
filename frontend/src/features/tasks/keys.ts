import type { TaskListParams } from "./types";

export const tasksKeys = {
  all: ["tasks"] as const,
  list: (params: TaskListParams) => [...tasksKeys.all, "list", params] as const,
  detail: (id: string) => [...tasksKeys.all, "detail", id] as const,
};
