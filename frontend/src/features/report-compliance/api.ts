import { api } from "@/lib/api-client";

import type { EmployeeCompliance } from "./types";

export const reportComplianceApi = {
  me: () => api.get<EmployeeCompliance>("/report-compliance/me"),
};
