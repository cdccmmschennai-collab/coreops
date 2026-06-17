export const plantMasterKeys = {
  all: ["plant-master"] as const,
  planningPlants: (activeOnly?: boolean) => [...plantMasterKeys.all, "planning-plants", activeOnly] as const,
  maintenancePlants: (activeOnly?: boolean) => [...plantMasterKeys.all, "maintenance-plants", activeOnly] as const,
};
