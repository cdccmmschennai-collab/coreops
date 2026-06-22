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

/** Maintenance Plant options for a Combobox, with each plant's parent Planning
 * Plant code/description joined in.
 *
 * Pass `planningPlantCode` to scope the list to a single Planning Plant — the
 * work-report task row uses this so a user only ever sees the Maintenance
 * Plants of the selected project's Planning Plant. Omit it to load all plants.
 * When `enabled` is false the fetch is skipped (no project selected yet). */
export function useMaintenancePlantOptions(
  activeOnly = true,
  planningPlantCode?: string,
  enabled = true,
) {
  const query = useQuery({
    queryKey: plantMasterKeys.maintenancePlants(activeOnly, planningPlantCode),
    queryFn: () => plantMasterApi.listMaintenancePlants(activeOnly, planningPlantCode),
    staleTime: 5 * 60 * 1000,
    enabled,
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
