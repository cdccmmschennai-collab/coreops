import { api } from "@/lib/api-client";
import type { ChangePasswordBody, Me, TokenResponse } from "@/types/api";

import type { LoginInput } from "./schemas";

export const authApi = {
  login: (input: LoginInput) => api.post<TokenResponse>("/auth/login", input),
  logout: () => api.post<void>("/auth/logout"),
  me: () => api.get<Me>("/auth/me"),
  changePassword: (body: ChangePasswordBody) =>
    api.post<void>("/auth/change-password", body),
};
