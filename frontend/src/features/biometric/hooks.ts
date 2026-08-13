import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { biometricApi } from "./api";
import { biometricKeys } from "./keys";

export function useExternalCodes(params: {
  provider: string;
  status: string;
  q: string;
  limit: number;
  offset: number;
}) {
  return useQuery({
    queryKey: biometricKeys.externalCodes(
      params.provider,
      params.status,
      params.q,
      params.limit,
      params.offset,
    ),
    queryFn: () =>
      biometricApi.listExternalCodes({
        provider: params.provider,
        status: params.status === "all" ? undefined : params.status,
        q: params.q,
        limit: params.limit,
        offset: params.offset,
      }),
    // Punch counts move whenever the connector runs; a short window keeps the
    // screen honest without polling.
    staleTime: 15 * 1000,
  });
}

/**
 * First IN / last OUT for one employee over a date range (the calendar month).
 *
 * Disabled without an employee id: the endpoint would then return every employee
 * a PM can see, which is not what a personal calendar wants.
 */
export function useDailySummary(params: {
  employeeId: string | undefined;
  from: string;
  to: string;
}) {
  return useQuery({
    queryKey: biometricKeys.dailySummary(
      params.employeeId ?? "",
      params.from,
      params.to,
    ),
    queryFn: () =>
      biometricApi.listDailySummary({
        employeeId: params.employeeId as string,
        from: params.from,
        to: params.to,
      }),
    enabled: !!params.employeeId,
    // Punches arrive when the connector runs, not continuously.
    staleTime: 60 * 1000,
  });
}

/** Employee picker search. Opens with the first page of active employees, then
 *  narrows as the PM types. React Query cancels the superseded request. */
export function useEmployeeSearch(q: string, enabled: boolean) {
  return useQuery({
    queryKey: biometricKeys.employeeSearch(q),
    queryFn: ({ signal }) => biometricApi.searchEmployees(q, signal),
    enabled,
    staleTime: 30 * 1000,
  });
}

function useInvalidateCodes() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: biometricKeys.all });
}

export function useCreateMapping() {
  const invalidate = useInvalidateCodes();
  return useMutation({
    mutationFn: biometricApi.createMapping,
    onSuccess: invalidate,
  });
}

export function useDeactivateMapping() {
  const invalidate = useInvalidateCodes();
  return useMutation({
    mutationFn: (mappingId: string) => biometricApi.deactivateMapping(mappingId),
    onSuccess: invalidate,
  });
}
