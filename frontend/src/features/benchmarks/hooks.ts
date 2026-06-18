import { useQuery } from "@tanstack/react-query";

import { benchmarksApi } from "./api";
import { benchmarksKeys } from "./keys";

export function useMyAlerts() {
  return useQuery({
    queryKey: benchmarksKeys.myAlerts(),
    queryFn: () => benchmarksApi.myAlerts(),
  });
}
