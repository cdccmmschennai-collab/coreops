import type { UserListParams } from "./types";

export const usersKeys = {
  all: ["users"] as const,
  list: (params: UserListParams) => ["users", "list", params] as const,
  detail: (id: string) => ["users", "detail", id] as const,
};
