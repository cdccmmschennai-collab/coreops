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

// ── pagination ──────────────────────────────────────────────────────────────

export interface Page<T> {
  items: T[];
  /** 1-based, clamped into [1, totalPages] */
  page: number;
  totalPages: number;
  total: number;
  /** 1-based index of the first row shown (0 when empty) */
  start: number;
  /** 1-based index of the last row shown (0 when empty) */
  end: number;
}

/** Parse a page number from the URL; anything invalid is page 1. */
export function parsePage(raw: string): number {
  const n = Number(raw);
  return Number.isInteger(n) && n >= 1 ? n : 1;
}

/**
 * Page buttons to render: every page when there are 7 or fewer, otherwise
 * first, last and a window around the current page, with "…" for gaps.
 */
export function pageNumbers(current: number, totalPages: number): (number | "…")[] {
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, i) => i + 1);
  const keep = new Set([1, totalPages, current - 1, current, current + 1]);
  const out: (number | "…")[] = [];
  for (let p = 1; p <= totalPages; p++) {
    if (!keep.has(p)) continue;
    const prev = out[out.length - 1];
    if (typeof prev === "number" && p - prev > 1) out.push("…");
    out.push(p);
  }
  return out;
}

/** Slice an already-filtered list. Non-overlapping, gap-free pages. */
export function paginate<T>(items: readonly T[], page: number, size = PAGE_SIZE): Page<T> {
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / size));
  const current = Math.min(Math.max(1, Math.floor(page) || 1), totalPages);
  const offset = (current - 1) * size;
  const slice = items.slice(offset, offset + size);
  return {
    items: slice,
    page: current,
    totalPages,
    total,
    start: total === 0 ? 0 : offset + 1,
    end: offset + slice.length,
  };
}
