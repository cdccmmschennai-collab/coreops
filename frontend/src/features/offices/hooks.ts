import { useQuery } from "@tanstack/react-query";

import { officesApi } from "./api";
import { officesKeys } from "./keys";

export function useOffices(enabled = true) {
  return useQuery({
    queryKey: officesKeys.list(),
    queryFn: () => officesApi.list(),
    enabled,
    staleTime: 5 * 60 * 1000, // offices rarely change — 5 min cache
  });
}
