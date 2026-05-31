import { api } from "@/lib/api-client";
import type { components } from "@/types/openapi";

export type UserAccount = components["schemas"]["UserOut"];
export type UserAccountPage = components["schemas"]["UserPage"];

export const usersApi = {
  list: () => api.get<UserAccountPage>("/users?limit=100"),
  get: (id: string) => api.get<UserAccount>(`/users/${id}`),
};
