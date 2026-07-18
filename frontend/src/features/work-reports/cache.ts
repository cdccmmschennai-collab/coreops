import type { QueryClient } from "@tanstack/react-query";

// Explicit .ts extension: this module is exercised directly by cache.test.ts
// under Node's ESM test runner, which does not do extensionless resolution.
// Permitted by allowImportingTsExtensions (see tsconfig.json) and resolved
// as-is by the Next bundler.
import { workReportKeys } from "./keys.ts";
import type { WorkReport } from "./types";

/**
 * Seed the React Query cache with a fresh create/update response.
 *
 * The detail entry is written FIRST via setQueryData, so the detail page
 * reached right after a save (router.push) renders the server's exact
 * response immediately — never a briefly-stale cached copy of the report.
 * The broad invalidation that follows only marks queries stale and refetches
 * them in the background; it never discards the just-written detail data, and
 * its eventual refetch returns the same newly-persisted report.
 *
 * Kept free of React so it can be unit-tested against a bare QueryClient.
 */
export function applyWorkReportToCache(
  queryClient: QueryClient,
  report: WorkReport,
): void {
  queryClient.setQueryData(workReportKeys.detail(report.id), report);
  void queryClient.invalidateQueries({ queryKey: workReportKeys.all });
}
