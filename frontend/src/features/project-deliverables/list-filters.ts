/**
 * Deliverables page filters: Project | Activity | Assignee | Status, plus
 * client-side pagination.
 *
 * Pure and framework-free (runs under `node --test`); imports are type-only.
 * Filtering is client-side over the already-scoped GET /deliverables list, so
 * every option list below is derived from rows the caller may already see -
 * no filter can surface an unauthorized project or person.
 */
import type { Deliverable } from "./types";

/** Sentinel for "no filter" - Radix Select cannot use an empty-string value. */
export const ALL = "all";
/** Assignee filter value matching deliverables with no Assignee. */
export const UNASSIGNED = "unassigned";
/** Deliverables per page. */
export const PAGE_SIZE = 10;

export interface DeliverableFilters {
  /** project_id, or ALL */
  project: string;
  /** exact activity (deliverable) name, or ALL ("" is treated as ALL) */
  activity: string;
  /** owner_employee_id, UNASSIGNED, or ALL */
  assignee: string;
  /** "planned" | "completed", or ALL */
  status: string;
}

export const NO_FILTERS: DeliverableFilters = {
  project: ALL,
  activity: ALL,
  assignee: ALL,
  status: ALL,
};

type FilterFields = Pick<Deliverable, "project_id" | "name" | "status" | "owner_employee_id">;

function isAll(v: string): boolean {
  return v === ALL || v.trim() === "";
}

export function filterDeliverables<T extends FilterFields>(
  items: readonly T[],
  f: DeliverableFilters,
): T[] {
  const activity = f.activity.trim();
  return items.filter(
    (d) =>
      (isAll(f.project) || d.project_id === f.project) &&
      (isAll(activity) || d.name.trim() === activity) &&
      (isAll(f.assignee) ||
        (f.assignee === UNASSIGNED ? !d.owner_employee_id : d.owner_employee_id === f.assignee)) &&
      (isAll(f.status) || d.status === f.status),
  );
}

export function isFiltered(f: DeliverableFilters): boolean {
  return !isAll(f.project) || !isAll(f.activity) || !isAll(f.assignee) || !isAll(f.status);
}

// ── dropdown options ────────────────────────────────────────────────────────

export interface FilterOption {
  value: string;
  label: string;
  /** secondary text (role) */
  sublabel?: string;
  /** extra search terms, not displayed */
  keywords?: string[];
}

/**
 * One option per project that actually has deliverables in the list, labelled
 * by code (falls back to name, then id), searchable by code AND name, sorted.
 */
export function projectFilterOptions(
  items: readonly Pick<Deliverable, "project_id" | "project_code" | "project_name">[],
): FilterOption[] {
  const seen = new Map<string, FilterOption>();
  for (const d of items) {
    if (seen.has(d.project_id)) continue;
    const label = d.project_code ?? d.project_name ?? d.project_id;
    const name = d.project_name?.trim();
    seen.set(d.project_id, {
      value: d.project_id,
      label,
      keywords: name && name !== label ? [name] : undefined,
    });
  }
  return [...seen.values()].sort((a, b) => a.label.localeCompare(b.label));
}

/** Distinct activity names in the list, sorted. */
export function activityFilterOptions(
  items: readonly Pick<Deliverable, "name">[],
): FilterOption[] {
  const names = new Set(items.map((d) => d.name.trim()).filter(Boolean));
  return [...names]
    .sort((a, b) => a.localeCompare(b))
    .map((name) => ({ value: name, label: name }));
}

/**
 * One option per distinct Assignee in the list (by employee id), name only,
 * sorted by name. "Unassigned" always comes last.
 */
export function assigneeFilterOptions(
  items: readonly Pick<Deliverable, "owner_employee_id" | "owner_name">[],
): FilterOption[] {
  const people = new Map<string, string>();
  for (const d of items) {
    if (d.owner_employee_id && !people.has(d.owner_employee_id)) {
      people.set(d.owner_employee_id, d.owner_name?.trim() || "Unknown");
    }
  }
  const options = [...people]
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label));
  return [...options, { value: UNASSIGNED, label: "Unassigned" }];
}

// ── pagination (same offset/limit model as the shared <Pagination>) ─────────

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  /** clamped onto a real page boundary */
  offset: number;
}

/** Parse `?offset=` from the URL; anything invalid is 0 (first page). */
export function parseOffset(raw: string | null | undefined): number {
  const n = Number(raw ?? "0");
  return Number.isInteger(n) && n > 0 ? n : 0;
}

/**
 * Slice an already-filtered list. Pages never overlap or skip rows; an
 * out-of-range offset (e.g. the list shrank) snaps to the last real page.
 */
export function paginate<T>(items: readonly T[], offset: number, limit = PAGE_SIZE): Page<T> {
  const total = items.length;
  const lastOffset = total === 0 ? 0 : Math.floor((total - 1) / limit) * limit;
  const aligned = Math.floor(Math.max(0, offset) / limit) * limit;
  const current = Math.min(aligned, lastOffset);
  return { items: items.slice(current, current + limit), total, limit, offset: current };
}

// ── return address (list -> detail -> back to the same list state) ──────────

export const DELIVERABLES_LIST_HREF = "/projects/deliverables";
export const DELIVERABLE_RETURN_PARAM = "from";

/** Detail URL carrying the list URL it was opened from (filters + page). */
export function deliverableDetailHref(id: string, from?: string | null): string {
  const base = `${DELIVERABLES_LIST_HREF}/${id}`;
  const target = (from ?? "").trim();
  return target ? `${base}?${DELIVERABLE_RETURN_PARAM}=${encodeURIComponent(target)}` : base;
}

/**
 * Where "← Deliverables" goes. Only the Deliverables list itself is accepted
 * as a return target; anything else (other routes, absolute or `//host` URLs,
 * look-alikes) falls back to the plain list - same rule as Leave Detail.
 */
export function deliverableReturnHref(raw: string | null | undefined): string {
  const target = (raw ?? "").trim();
  const [path] = target.split("?");
  return path === DELIVERABLES_LIST_HREF ? target : DELIVERABLES_LIST_HREF;
}
