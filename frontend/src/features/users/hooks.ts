import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { usersApi } from "./api";
import { usersKeys } from "./keys";
import type { UserCreateBody, UserListParams, UserUpdateBody } from "./types";

/** List users (admin only) — used to populate the user-account-link select. */
export function useUsers(enabled = true) {
  return useQuery({
    queryKey: ["users", "list"],
    queryFn: () => usersApi.list(),
    enabled,
  });
}

/** Fetch one user (admin only) — linked-account email + detail page. */
export function useUser(id: string | null | undefined, enabled = true) {
  return useQuery({
    queryKey: usersKeys.detail(id ?? ""),
    queryFn: () => usersApi.get(id as string),
    enabled: enabled && !!id,
  });
}

// ---------- management (Settings → Users & Roles) ----------
export function useUsersList(params: UserListParams) {
  return useQuery({
    queryKey: usersKeys.list(params),
    queryFn: () => usersApi.listPaged(params),
    placeholderData: (prev) => prev,
  });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: UserCreateBody) => usersApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: usersKeys.all }),
  });
}

export function useUpdateUser(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: UserUpdateBody) => usersApi.update(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: usersKeys.all });
      qc.invalidateQueries({ queryKey: usersKeys.detail(id) });
    },
  });
}

export function useSetPassword(id: string) {
  return useMutation({
    mutationFn: (newPassword: string) => usersApi.setPassword(id, newPassword),
  });
}
