import { api } from "@/lib/api-client";

import type { MaintenancePlant, PlanningPlant } from "./types";

export const plantMasterApi = {
  listPlanningPlants: (activeOnly = true) =>
    api.get<PlanningPlant[]>(`/plants/planning-plants?active_only=${activeOnly}`),
  /** When `planningPlantCode` is given, the backend returns only the
   *  Maintenance Plants belonging to that Planning Plant (project-scoped
   *  dropdown for the work-report form). */
  listMaintenancePlants: (activeOnly = true, planningPlantCode?: string) => {
    const params = new URLSearchParams({ active_only: String(activeOnly) });
    if (planningPlantCode) params.set("planning_plant_code", planningPlantCode);
    return api.get<MaintenancePlant[]>(`/plants/maintenance-plants?${params.toString()}`);
  },
};
