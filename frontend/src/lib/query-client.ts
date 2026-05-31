/** TanStack Query client factory with centralized 401 handling. */
import { QueryCache, QueryClient } from "@tanstack/react-query";

import { AppError } from "./api-client";
import { clearToken } from "./auth-storage";

function handleUnauthorized(error: unknown): void {
  if (error instanceof AppError && error.status === 401) {
    clearToken();
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      const next = encodeURIComponent(window.location.pathname);
      window.location.assign(`/login?next=${next}`);
    }
  }
}

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({ onError: handleUnauthorized }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: (count, error) => {
          // Never retry 4xx; retry transient errors up to twice.
          if (error instanceof AppError && error.status >= 400 && error.status < 500) {
            return false;
          }
          return count < 2;
        },
      },
    },
  });
}
