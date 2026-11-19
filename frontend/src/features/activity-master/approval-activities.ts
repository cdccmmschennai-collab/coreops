/**
 * Approval Activities picker logic (Rework Activity Approval, migration 0090).
 *
 * Pure, dependency-free so `node --test` can pin it. The Settings section feeds
 * it the flat sub-activity index and renders the groups it returns.
 *
 * "Rework" in a name is ONLY a search hint for finding candidates - it never
 * decides approval. Approval is the explicit `requires_pm_approval` flag an
 * administrator sets per sub-activity.
 */

import { normalizeSearchTerm } from "./search.ts";
import type { SubActivityFlat } from "./types";

/** "Rework", "Re-work", "Re work", any case, as a word start ("CABLE-REWORK"
 *  counts; "FIREWORKS" does not). */
const REWORK_PATTERN = /(^|[^a-z0-9])re[\s-]?work/i;

export function isReworkCandidate(name: string): boolean {
  return REWORK_PATTERN.test(name);
}

export interface CandidateGroup {
  activityId: string;
  activityName: string;
  /** Sub-activities that can still be added, in source order. */
  subs: SubActivityFlat[];
}

export interface CandidateOptions {
  /** Only sub-activities whose name looks like rework. */
  reworkOnly?: boolean;
}

/**
 * Sub-activities that are NOT yet configured, grouped under their parent
 * Activity. A term matching the Activity's name shows all of its remaining
 * sub-activities; otherwise only sub-activities whose own name matches.
 * Groups with nothing left to add are dropped. Source order is preserved.
 */
export function groupApprovalCandidates(
  subs: readonly SubActivityFlat[],
  rawTerm: string,
  options: CandidateOptions = {},
): CandidateGroup[] {
  const term = normalizeSearchTerm(rawTerm);
  const groups = new Map<string, CandidateGroup>();
  for (const sub of subs) {
    if (sub.requires_pm_approval) continue;
    if (options.reworkOnly && !isReworkCandidate(sub.name)) continue;
    if (term) {
      const inActivity = normalizeSearchTerm(sub.activity_name).includes(term);
      const inSub = normalizeSearchTerm(sub.name).includes(term);
      if (!inActivity && !inSub) continue;
    }
    let group = groups.get(sub.activity_id);
    if (!group) {
      group = { activityId: sub.activity_id, activityName: sub.activity_name, subs: [] };
      groups.set(sub.activity_id, group);
    }
    group.subs.push(sub);
  }
  return [...groups.values()];
}
