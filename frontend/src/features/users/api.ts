import { api } from "@/lib/api-client";
import type { components } from "@/types/openapi";

import type {
  User,
  UserCreateBody,
  UserListParams,
  UserPage,
  UserUpdateBody,
} from "./types";

// Back-compat aliases used by the employees selects (do not remove).
export type UserAccount = components["schemas"]["UserOut"];
export type UserAccountPage = components["schemas"]["UserPage"];

function toQuery(p: UserListParams): string {
  const sp = new URLSearchParams();
  if (p.q) sp.set("q", p.q);
  sp.set("limit", String(p.limit));
  sp.set("offset", String(p.offset));
  return sp.toString();
}

export const usersApi = {
  // existing — used by employee user-account select + linked-email display
  list: () => api.get<UserAccountPage>("/users?limit=100"),
  get: (id: string) => api.get<UserAccount>(`/users/${id}`),

  // management (Settings → Users & Roles)
  listPaged: (params: UserListParams) => api.get<UserPage>(`/users?${toQuery(params)}`),
  create: (body: UserCreateBody) => api.post<User>("/users", body),
  update: (id: string, body: UserUpdateBody) => api.patch<User>(`/users/${id}`, body),
  setPassword: (id: string, newPassword: string) =>
    api.patch<void>(`/users/${id}/password`, { new_password: newPassword }),
};
