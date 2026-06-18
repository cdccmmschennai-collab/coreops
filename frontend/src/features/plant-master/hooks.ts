import { useQuery } from "@tanstack/react-query";

import { plantMasterApi } from "./api";
import { plantMasterKeys } from "./keys";

export function usePlanningPlants(activeOnly = true) {
  return useQuery({
    queryKey: plantMasterKeys.planningPlants(activeOnly),
    queryFn: () => plantMasterApi.listPlanningPlants(activeOnly),
    staleTime: 5 * 60 * 1000,
  });
}

/** Flat list of every active Maintenance Plant, with its parent Planning
 * Plant's code/description joined in — the source for the Combobox used on
 * both the Project form and the Work Report task row. Pick the Maintenance
 * Plant directly; Planning Plant info auto-derives from `byId`. */
export function useMaintenancePlantOptions(activeOnly = true) {
  const query = useQuery({
    queryKey: plantMasterKeys.maintenancePlants(activeOnly),
    queryFn: () => plantMasterApi.listMaintenancePlants(activeOnly),
    staleTime: 5 * 60 * 1000,
  });
  const items = query.data ?? [];
  const byId = new Map(items.map((mp) => [mp.id, mp]));
  const options = items.map((mp) => ({
    value: mp.id,
    label: mp.code,
    sublabel: mp.description ?? undefined,
  }));
  return { items, byId, options, isLoading: query.isLoading };
}
