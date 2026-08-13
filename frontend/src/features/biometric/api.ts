import { api } from "@/lib/api-client";

import type {
  DailySummaryPage,
  EmployeeMapping,
  EmployeePage,
  ExternalCodePage,
} from "./types";

import { PROVIDER_EASYTIME } from "./types";

const BASE = "/biometric";

export const biometricApi = {
  /** Distinct EasyTime codes seen in the raw punch log, with their mapping
   *  state. Read-only - it creates nothing and proposes nothing. */
  listExternalCodes: (params: {
    provider: string;
    status?: string;
    q?: string;
    limit: number;
    offset: number;
  }) => {
    const sp = new URLSearchParams({
      provider: params.provider,
      limit: String(params.limit),
      offset: String(params.offset),
    });
    if (params.status) sp.set("status", params.status);
    if (params.q?.trim()) sp.set("q", params.q.trim());
    return api.get<ExternalCodePage>(`${BASE}/external-codes?${sp.toString()}`);
  },

  /** The authoritative single-mapping path. Re-pointing a code deactivates the
   *  previous row server-side; this client never edits a mapping in place. */
  createMapping: (body: {
    provider: string;
    external_employee_code: string;
    employee_id: string;
  }) => api.post<EmployeeMapping>(`${BASE}/mappings`, body),

  deactivateMapping: (mappingId: string) =>
    api.del<EmployeeMapping>(`${BASE}/mappings/${mappingId}`),

  /** First IN / last OUT per attendance day. Read-only observation - it is not
   *  an attendance record and it writes nothing. */
  listDailySummary: (params: {
    employeeId: string;
    from: string;
    to: string;
    provider?: string;
  }) => {
    const sp = new URLSearchParams({
      provider: params.provider ?? PROVIDER_EASYTIME,
      employee_id: params.employeeId,
      from: params.from,
      to: params.to,
    });
    return api.get<DailySummaryPage>(`${BASE}/daily-summary?${sp.toString()}`);
  },

  /** Server-side employee search for the picker. Active employees only, so a
   *  mapping cannot be pointed at someone who has left. */
  searchEmployees: (q: string, signal?: AbortSignal) => {
    const sp = new URLSearchParams({
      status: "active",
      limit: "20",
      offset: "0",
    });
    if (q.trim()) sp.set("q", q.trim());
    return api.get<EmployeePage>(`/employees?${sp.toString()}`, signal);
  },
};
