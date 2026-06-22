export const plantMasterKeys = {
  all: ["plant-master"] as const,
  planningPlants: (activeOnly?: boolean) => [...plantMasterKeys.all, "planning-plants", activeOnly] as const,
  maintenancePlants: (activeOnly?: boolean, planningPlantCode?: string) =>
    [...plantMasterKeys.all, "maintenance-plants", activeOnly, planningPlantCode ?? null] as const,
};
