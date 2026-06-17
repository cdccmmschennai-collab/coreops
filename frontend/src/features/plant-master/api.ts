import { api } from "@/lib/api-client";

import type { MaintenancePlant, PlanningPlant } from "./types";

export const plantMasterApi = {
  listPlanningPlants: (activeOnly = true) =>
    api.get<PlanningPlant[]>(`/plants/planning-plants?active_only=${activeOnly}`),
  listMaintenancePlants: (activeOnly = true) =>
    api.get<MaintenancePlant[]>(`/plants/maintenance-plants?active_only=${activeOnly}`),
};
