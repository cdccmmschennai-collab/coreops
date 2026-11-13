/**
 * Deliverable Detail page - pure display helpers.
 *
 * Framework-free so it runs under `node --test`. Imports are type-only.
 */

/** What the "Project Head" row shows, derived from the GET /projects/{id} query. */
export type ProjectHeadDisplay =
  | { kind: "loading" }
  | { kind: "unavailable" }
  | { kind: "assigned"; name: string }
  | { kind: "not_assigned" };

/**
 * Map the project query to the Project Head row.
 *
 * A failed lookup is "unavailable", never "Not assigned": showing "Not
 * assigned" when we simply could not read the project would state something
 * false about real data. A head id without a resolvable name is treated the
 * same way for the same reason.
 */
export function projectHeadDisplay(q: {
  isLoading: boolean;
  isError: boolean;
  data?: { head_employee_id?: string | null; head_employee_name?: string | null } | null;
}): ProjectHeadDisplay {
  if (q.isLoading) return { kind: "loading" };
  if (q.isError || !q.data) return { kind: "unavailable" };
  const name = q.data.head_employee_name?.trim();
  if (name) return { kind: "assigned", name };
  if (q.data.head_employee_id) return { kind: "unavailable" };
  return { kind: "not_assigned" };
}

export const PROJECT_HEAD_TEXT: Record<Exclude<ProjectHeadDisplay["kind"], "loading" | "assigned">, string> = {
  not_assigned: "Not assigned",
  unavailable: "Unavailable",
};

/**
 * The Assignee as both the table and the Details card show it: just the name,
 * or "Unassigned". An id whose name could not be resolved is shown as
 * "Unknown" rather than "Unassigned" - it IS assigned.
 */
export function assigneeDisplay(d: {
  owner_employee_id: string | null;
  owner_name: string | null;
}): { assigned: boolean; name: string } {
  if (!d.owner_employee_id) return { assigned: false, name: "Unassigned" };
  return { assigned: true, name: d.owner_name?.trim() || "Unknown" };
}

/** Project row: bold number + optional secondary description. Falls back to
 *  the id only when the project has no code, so the link is never empty. */
export function projectLabel(d: {
  project_id: string;
  project_code: string | null;
  project_name: string | null;
}): { number: string; description: string | null } {
  const number = d.project_code?.trim() || d.project_name?.trim() || d.project_id;
  const description =
    d.project_name && d.project_name.trim() && d.project_name.trim() !== number
      ? d.project_name.trim()
      : null;
  return { number, description };
}

/**
 * Countdown for the Details card corner, from the backend's signed
 * `days_remaining` (never the browser clock). Null = show nothing: completed
 * (the status badge already says so) or no deadline set.
 */
export function daysLeftLabel(d: {
  deadline_state: string;
  days_remaining: number | null;
}): string | null {
  if (d.deadline_state === "completed" || d.days_remaining === null) return null;
  const n = d.days_remaining;
  if (n === 0) return "Due today";
  const abs = Math.abs(n);
  const unit = abs === 1 ? "day" : "days";
  return n > 0 ? `${abs} ${unit} left` : `${abs} ${unit} overdue`;
}

/** Exact route of the Project Detail page (unchanged from before the redesign). */
export function projectHref(projectId: string): string {
  return `/projects/${projectId}`;
}
