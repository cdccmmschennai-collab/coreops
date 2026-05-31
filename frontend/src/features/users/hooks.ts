import { useQuery } from "@tanstack/react-query";

import { usersApi } from "./api";

/** List users (admin only) — used to populate the user-account-link select. */
export function useUsers(enabled = true) {
  return useQuery({
    queryKey: ["users", "list"],
    queryFn: () => usersApi.list(),
    enabled,
  });
}

/** Fetch one user (admin only) — used to show a linked account's email. */
export function useUser(id: string | null | undefined, enabled = true) {
  return useQuery({
    queryKey: ["users", "detail", id ?? ""],
    queryFn: () => usersApi.get(id as string),
    enabled: enabled && !!id,
  });
}
