/**
 * Deliverables page filters: Project | Activity | Status.
 *
 * Pure and framework-free (runs under `node --test`); imports are type-only.
 * Filtering is client-side over the already-scoped GET /deliverables list.
 */
import type { Deliverable } from "./types";

/** Sentinel for "no filter" - Radix Select cannot use an empty-string value. */
export const ALL = "all";

export interface DeliverableFilters {
  /** project_id, or ALL */
  project: string;
  /** free-text match on the activity (deliverable) name; "" = no filter */
  activity: string;
  /** "planned" | "completed", or ALL */
  status: string;
}

type FilterFields = Pick<Deliverable, "project_id" | "name" | "status">;

export function filterDeliverables<T extends FilterFields>(
  items: readonly T[],
  f: DeliverableFilters,
): T[] {
  const needle = f.activity.trim().toLowerCase();
  return items.filter(
    (d) =>
      (f.project === ALL || d.project_id === f.project) &&
      (f.status === ALL || d.status === f.status) &&
      (needle === "" || d.name.toLowerCase().includes(needle)),
  );
}

export function isFiltered(f: DeliverableFilters): boolean {
  return f.project !== ALL || f.status !== ALL || f.activity.trim() !== "";
}

export interface ProjectFilterOption {
  id: string;
  label: string;
}

/**
 * One option per project that actually has deliverables in the list, labelled
 * by code (falls back to name, then id), sorted by label.
 */
export function projectFilterOptions(
  items: readonly Pick<Deliverable, "project_id" | "project_code" | "project_name">[],
): ProjectFilterOption[] {
  const seen = new Map<string, string>();
  for (const d of items) {
    if (!seen.has(d.project_id)) {
      seen.set(d.project_id, d.project_code ?? d.project_name ?? d.project_id);
    }
  }
  return [...seen]
    .map(([id, label]) => ({ id, label }))
    .sort((a, b) => a.label.localeCompare(b.label));
}
