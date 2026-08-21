import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-provider";
import { useActivityStaffing } from "@/features/projects/hooks";

import { productionStatusApi } from "./api";
import { productionStatusKeys } from "./keys";
import { leadsAnyActivity } from "./production-status";
import type {
  ProductionStatusCreateBody,
  ProductionStatusHistoryParams,
} from "./types";

/**
 * Is the current user the Lead of any activity on this project?
 *
 * The third arm of the Production Status read rule (PM / Head / activity Lead),
 * and the only one that needs data the project row does not carry. Resolved
 * from the project's activity staffing — the very same join the backend
 * authorizes on — so the tab appears for exactly the people the API will serve.
 *
 * Deliberately a separate hook from `useProjectAuthority`, which stays a pure
 * derivation with no request of its own: the /edit page consults that one and
 * has no reason to fetch staffing. On the detail page the query is already in
 * flight for the Members card, so this costs no extra round trip.
 */
export function useLeadsAnyActivity(projectId: string | undefined): boolean {
  const { employeeId } = useAuth();
  const staffing = useActivityStaffing(projectId);
  return leadsAnyActivity(staffing.data, employeeId);
}

/**
 * Current production status for the project.
 *
 * `enabled` carries the caller's read authority: the endpoint is PM / Head /
 * activity-Lead only, so a viewer without it must not fire a request that is
 * guaranteed to come back 403 (the tab is not rendered for them either way).
 */
export function useLatestProductionStatus(
  projectId: string | undefined,
  enabled = true,
) {
  return useQuery({
    queryKey: productionStatusKeys.latest(projectId ?? ""),
    queryFn: () => productionStatusApi.listLatest(projectId as string),
    enabled: !!projectId && enabled,
  });
}

/**
 * The append-only trail. Gated on `enabled` so the history only loads when the
 * user actually opens it - the current view is what the tab leads with.
 */
export function useProductionStatusHistory(
  projectId: string | undefined,
  params: ProductionStatusHistoryParams,
  enabled = true,
) {
  return useQuery({
    queryKey: productionStatusKeys.history(projectId ?? "", params),
    queryFn: () => productionStatusApi.listHistory(projectId as string, params),
    enabled: !!projectId && enabled,
  });
}

/**
 * Append one update.
 *
 * Invalidates rather than patching the cache by hand: "latest" is derived
 * server-side (newest row per revision+activity), so the client must not guess
 * whether the row it just saved is the current one - it asks. Every history
 * query for the project is invalidated too, because the new row belongs at the
 * top of its own activity/revision trail and of the unfiltered list.
 */
/**
 * The PM cumulative report.
 *
 * ONE query for every project. `enabled` carries both the caller's authority
 * and the dialog's open state: the endpoint is PM-only, so a non-PM must not
 * fire a request guaranteed to come back 403 (they never see the button
 * either), and the report is not fetched at all until the PM opens it - the
 * projects list must not pay for a report nobody asked for.
 *
 * `month` ("2026-08", or undefined for All Months) is part of the query key, so
 * changing the dropdown refetches instead of showing another month's rows, and
 * a month already looked at comes back from the cache. The filtering itself is
 * entirely the server's - this hook narrows the request, never the response.
 */
export function useProductionStatusReport(enabled: boolean, month?: string) {
  return useQuery({
    queryKey: productionStatusKeys.report(month),
    queryFn: () => productionStatusApi.report(month),
    enabled,
    // The months on offer come with the report, so they would blink away on
    // every switch if the previous data were dropped. Keeping it also stops the
    // table flashing empty between months.
    placeholderData: (prev) => prev,
  });
}

export function useCreateProductionStatus(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProductionStatusCreateBody) =>
      productionStatusApi.create(projectId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: productionStatusKeys.latest(projectId) });
      qc.invalidateQueries({
        queryKey: ["production-status", "history", projectId],
      });
    },
  });
}
