"use client";

import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { clearToken, getToken, setToken } from "@/lib/auth-storage";
import type { EmployeeProfile, Role, User } from "@/types/api";

import { authApi } from "./api";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  user: User | undefined;
  role: Role | undefined;
  employee: EmployeeProfile | null;
  employeeId: string | null;
  login: (accessToken: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export const AUTH_ME_KEY = ["auth", "me"] as const;

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [token, setTokenState] = React.useState<string | null>(null);
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setTokenState(getToken());
    setMounted(true);
  }, []);

  const meQuery = useQuery({
    queryKey: AUTH_ME_KEY,
    queryFn: authApi.me,
    enabled: mounted && !!token,
    retry: false,
  });

  const login = React.useCallback(
    async (accessToken: string) => {
      setToken(accessToken);
      setTokenState(accessToken);
      await queryClient.invalidateQueries({ queryKey: AUTH_ME_KEY });
    },
    [queryClient],
  );

  const logout = React.useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // Best-effort server revocation; always clear locally.
    }
    clearToken();
    setTokenState(null);
    queryClient.clear();
  }, [queryClient]);

  let status: AuthStatus;
  if (!mounted) status = "loading";
  else if (!token) status = "unauthenticated";
  else if (meQuery.isSuccess) status = "authenticated";
  else if (meQuery.isError) status = "unauthenticated";
  else status = "loading";

  const user = meQuery.data?.user;

  const value: AuthContextValue = {
    status,
    user,
    role: user?.role,
    employee: meQuery.data?.employee ?? null,
    employeeId: meQuery.data?.employee_id ?? null,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
