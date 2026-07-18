/**
 * Regression guard for the post-save cache seed.
 *
 * Second half of the "saved 83, saw 81" report: even once the PATCH carries
 * the right number, the detail page reached by router.push() must render the
 * server's response immediately. If the save only invalidated queries, the
 * detail route would paint the previously-cached report (81) for one frame
 * before the refetch landed — indistinguishable, to the user, from a bad save.
 *
 * applyWorkReportToCache therefore writes the response with setQueryData
 * FIRST, then invalidates. These tests pin that ordering and, crucially, that
 * the broad list invalidation does not discard the just-written detail entry.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { QueryClient } from "@tanstack/react-query";

import { applyWorkReportToCache } from "./cache.ts";
import { workReportKeys } from "./keys.ts";
import type { WorkReport } from "./types.ts";

/** Minimal report stand-in; only id and the count under test matter here. */
function report(id: string, tagsCount: number): WorkReport {
  return {
    id,
    tasks: [{ id: `${id}-t1`, tags_count: tagsCount }],
  } as unknown as WorkReport;
}

/** A QueryClient with retries off so nothing refetches behind the assertions. */
function newClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
}

function cachedTagsCount(qc: QueryClient, id: string): number | undefined {
  const cached = qc.getQueryData<WorkReport>(workReportKeys.detail(id));
  return cached?.tasks[0]?.tags_count;
}

test("the PATCH response is written to the detail cache", () => {
  const qc = newClient();

  applyWorkReportToCache(qc, report("r1", 83));

  assert.equal(cachedTagsCount(qc, "r1"), 83);
});

test("the response overwrites a stale cached count", () => {
  const qc = newClient();
  // The detail page was visited before the edit and cached 81.
  qc.setQueryData(workReportKeys.detail("r1"), report("r1", 81));

  applyWorkReportToCache(qc, report("r1", 83));

  // Not 81: the navigation that follows must never paint the old number.
  assert.equal(cachedTagsCount(qc, "r1"), 83);
});

test("invalidation does not discard the newly written detail data", () => {
  const qc = newClient();
  qc.setQueryData(workReportKeys.detail("r1"), report("r1", 81));

  applyWorkReportToCache(qc, report("r1", 83));

  // workReportKeys.all is a prefix of detail(), so the invalidation DOES match
  // the detail query. Invalidation must only mark it stale for a background
  // refetch — the data itself has to survive, or the detail page renders
  // undefined (a loading flash) or the old report.
  const entry = qc.getQueryCache().find({ queryKey: workReportKeys.detail("r1") });
  assert.equal(cachedTagsCount(qc, "r1"), 83);
  assert.notEqual(entry?.state.data, undefined);
});

test("a report reached immediately after save reads the returned value", () => {
  const qc = newClient();
  qc.setQueryData(workReportKeys.detail("r1"), report("r1", 81));

  applyWorkReportToCache(qc, report("r1", 83));

  // Simulates the detail route mounting synchronously after router.push():
  // it reads the cache before any refetch could possibly have resolved.
  const onMount = qc.getQueryData<WorkReport>(workReportKeys.detail("r1"));
  assert.equal(onMount?.tasks[0]?.tags_count, 83);
});

test("only the saved report's detail entry is rewritten", () => {
  const qc = newClient();
  qc.setQueryData(workReportKeys.detail("r2"), report("r2", 40));

  applyWorkReportToCache(qc, report("r1", 83));

  // A sibling report's cached copy is left alone, not clobbered or emptied.
  assert.equal(cachedTagsCount(qc, "r2"), 40);
});

test("list queries are marked stale so the list picks the new count up", () => {
  const qc = newClient();
  const listKey = workReportKeys.list({} as never);
  qc.setQueryData(listKey, [report("r1", 81)]);

  applyWorkReportToCache(qc, report("r1", 83));

  const listEntry = qc.getQueryCache().find({ queryKey: listKey });
  assert.equal(listEntry?.state.isInvalidated, true);
});
