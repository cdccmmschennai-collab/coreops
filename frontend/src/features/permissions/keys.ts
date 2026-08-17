import type { PermissionListParams } from "./types";

export const permissionKeys = {
  all: ["permissions"] as const,
  list: (params: PermissionListParams) => [...permissionKeys.all, "list", params] as const,
  detail: (id: string) => [...permissionKeys.all, "detail", id] as const,
  history: (month: string, employeeId?: string) =>
    [...permissionKeys.all, "history", month, employeeId ?? ""] as const,
  myBalance: (month?: string) => [...permissionKeys.all, "balance", "me", month ?? ""] as const,
  balance: (employeeId: string, month?: string) =>
    [...permissionKeys.all, "balance", employeeId, month ?? ""] as const,
};
