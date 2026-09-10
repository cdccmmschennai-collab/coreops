/**
 * Unified Activity + Sub-Activity search for the Activity Master.
 *
 * Pure, dependency-free (no React, no DOM) so `node --test` can pin the
 * behaviour. The manager component feeds it the two datasets it already loads
 * (top-level activities + the flat sub-activity list) and renders whatever
 * comes back:
 *
 *     searchTerm
 *         -> match activities (code + name) and sub-activities (name)
 *         -> group sub-activity hits under their parent
 *         -> visible activities, ranked
 *         -> parents to auto-expand + the single primary row to highlight
 *
 * Search state is DERIVED. Nothing here touches the user's own expansion
 * state; the component overlays `expandActivityIds` while a term is active
 * and drops it the moment the term is cleared.
 */

import type { ActivityMaster, SubActivityFlat } from "./types";

/** Lower-cased, trimmed, inner whitespace collapsed to single spaces. */
export function normalizeSearchTerm(raw: string): string {
  return raw.trim().replace(/\s+/g, " ").toLowerCase();
}

/**
 * Relevance tiers, lower = better. Ranking is by tier first, then by the
 * source ordering (sort_order / name, as the API returns it) so results are
 * deterministic - never by plain `includes()`.
 *
 *   0  exact activity name / code
 *   1  exact sub-activity name (an exact match always beats any prefix)
 *   2  activity name starts with the term
 *   3  activity code starts with the term
 *   4  sub-activity name starts with the term
 *   5  a whole word inside the text starts with the term ("MTL PROCESS" for "PROCESS")
 *   6  the term occurs inside the text but not at a word start ("FMTL" for "MTL")
 */
export type MatchTier = 0 | 1 | 2 | 3 | 4 | 5 | 6;

/** How a single text field matches the (normalized) term. */
type FieldMatch = "exact" | "prefix" | "word" | "contains" | null;

function matchField(text: string | null | undefined, term: string): FieldMatch {
  if (!text) return null;
  const value = normalizeSearchTerm(text);
  if (value === term) return "exact";
  if (value.startsWith(term)) return "prefix";
  const idx = value.indexOf(term);
  if (idx < 0) return null;
  // "Word start": the character before the hit is not alphanumeric. Covers
  // spaces and punctuation ("FMTL-REWORK" for "REWORK"), but "FMTL" for "MTL"
  // sits mid-word and stays a plain contains.
  return /[a-z0-9]/.test(value[idx - 1] ?? "") ? "contains" : "word";
}

function activityTier(a: ActivityMaster, term: string): MatchTier | null {
  const name = matchField(a.name, term);
  const code = matchField(a.code, term);
  if (name === "exact" || code === "exact") return 0;
  if (name === "prefix") return 2;
  if (code === "prefix") return 3;
  if (name === "word" || code === "word") return 5;
  if (name === "contains" || code === "contains") return 6;
  return null;
}

function subActivityTier(s: SubActivityFlat, term: string): MatchTier | null {
  const name = matchField(s.name, term);
  if (name === "exact") return 1;
  if (name === "prefix") return 4;
  if (name === "word") return 5;
  if (name === "contains") return 6;
  return null;
}

export interface SubActivityHit {
  sub: SubActivityFlat;
  tier: MatchTier;
}

export interface ActivityResult {
  activity: ActivityMaster;
  /** The activity's own code/name match, if any. */
  activityTier: MatchTier | null;
  /** Children whose name matched, in source order. Empty when only the
   *  activity itself matched. */
  subHits: SubActivityHit[];
  /** Best tier across the activity and its children - the sort key. */
  bestTier: MatchTier;
}

export interface SearchResult {
  /** Empty term -> not searching; the component shows the plain list. */
  active: boolean;
  /** Activities to render, best match first. Untouched source list when
   *  `active` is false. */
  activities: ActivityResult[];
  /** Parents to auto-expand while this term is active: every activity with
   *  at least one matching child. Activities that matched only by their own
   *  name are NOT expanded (the user asked for the activity, not its children). */
  expandActivityIds: string[];
  /** Ids of every matching sub-activity, for per-row emphasis. */
  matchedSubActivityIds: string[];
  /** The one row to scroll to and flash: the best sub-activity hit, or null
   *  when no sub-activity matched. Ties resolve to source order, so the exact
   *  match always wins over prefix/contains. */
  primary: { subActivityId: string; activityId: string } | null;
}

export function searchActivityMaster(
  activities: readonly ActivityMaster[],
  subActivities: readonly SubActivityFlat[],
  rawTerm: string,
): SearchResult {
  const term = normalizeSearchTerm(rawTerm);
  if (!term) {
    return {
      active: false,
      activities: activities.map((activity) => ({
        activity,
        activityTier: null,
        subHits: [],
        bestTier: 6,
      })),
      expandActivityIds: [],
      matchedSubActivityIds: [],
      primary: null,
    };
  }

  // Sub-activity hits grouped by parent, preserving the API's source order.
  const hitsByParent = new Map<string, SubActivityHit[]>();
  for (const sub of subActivities) {
    const tier = subActivityTier(sub, term);
    if (tier === null) continue;
    const list = hitsByParent.get(sub.activity_id) ?? [];
    list.push({ sub, tier });
    hitsByParent.set(sub.activity_id, list);
  }

  const results: ActivityResult[] = [];
  for (const activity of activities) {
    const aTier = activityTier(activity, term);
    const subHits = hitsByParent.get(activity.id) ?? [];
    if (aTier === null && subHits.length === 0) continue;
    const bestTier = Math.min(
      aTier ?? 6,
      ...subHits.map((h) => h.tier),
    ) as MatchTier;
    results.push({ activity, activityTier: aTier, subHits, bestTier });
  }
  // Stable sort: tier first, source order as the tiebreak (Array.prototype.sort
  // is stable in every engine the app targets).
  results.sort((x, y) => x.bestTier - y.bestTier);

  let primary: SearchResult["primary"] = null;
  let primaryTier: MatchTier = 6;
  const matchedSubActivityIds: string[] = [];
  for (const r of results) {
    for (const h of r.subHits) {
      matchedSubActivityIds.push(h.sub.id);
      // Strictly-better only: the first hit in ranked order holds a tie.
      if (primary === null || h.tier < primaryTier) {
        primary = { subActivityId: h.sub.id, activityId: r.activity.id };
        primaryTier = h.tier;
      }
    }
  }

  return {
    active: true,
    activities: results,
    expandActivityIds: results.filter((r) => r.subHits.length > 0).map((r) => r.activity.id),
    matchedSubActivityIds,
    primary,
  };
}
