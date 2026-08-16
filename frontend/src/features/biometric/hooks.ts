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

/**
 * One attendance day across the whole roster, for PM review.
 *
 * `classification` is applied server-side, so switching the filter is a new
 * query rather than a client-side re-filter - the row set and the day's counts
 * then always come from the same source and cannot disagree.
 */
export function useDailyReview(params: {
  date: string;
  classification?: string;
  q?: string;
  limit: number;
  offset: number;
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: biometricKeys.dailyReview(
      params.date,
      params.classification ?? "all",
      params.q ?? "",
      params.limit,
      params.offset,
    ),
    queryFn: () =>
      biometricApi.listDailyReview({
        date: params.date,
        classification: params.classification,
        q: params.q,
        limit: params.limit,
        offset: params.offset,
      }),
    enabled: params.enabled !== false && !!params.date,
    // Punches arrive when the connector runs, not continuously.
    staleTime: 60 * 1000,
    // Keeps the table from flashing to a skeleton on every keystroke/page turn.
    placeholderData: (prev) => prev,
  });
}

/** One employee, one day - the Phase 9B PM detail screen. */
export function useDailyReviewDetail(params: {
  employeeId: string;
  date: string;
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: biometricKeys.dailyReviewDetail(params.employeeId, params.date),
    queryFn: () =>
      biometricApi.getDailyReviewDetail({
        employeeId: params.employeeId,
        date: params.date,
      }),
    enabled: params.enabled !== false && !!params.employeeId && !!params.date,
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
