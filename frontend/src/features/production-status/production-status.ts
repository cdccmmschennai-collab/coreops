/**
 * Production Status presentation + policy logic (Phase 2).
 *
 * Everything the tab decides - which activities a viewer may submit for, what
 * every cell says, which empty state applies, how an error reads - is decided
 * here, and the components only render the result. That split is what makes
 * the tab testable: the repo's `node --test` harness has no jsdom or React
 * Testing Library, so logic living inside JSX cannot be covered at all.
 *
 * This module computes NOTHING about production itself. It never sums counts,
 * never derives a status, never works out which update is "current" - all of
 * that is the backend's (see `production_status/service.py`, where "latest" is
 * a DISTINCT ON over the append-only table). The rows arrive finished; this
 * file only turns them into strings.
 *
 * Deliberately dependency-free (like scope.ts, tabs.ts and summary.ts) so
 * `node --test` can cover it without a bundler. The interfaces below are
 * structural stand-ins for the generated openapi types - TypeScript matches
 * them by shape, so the components can pass API objects straight in.
 */

// ---------------------------------------------------------------------------
// Status vocabulary - the Phase 1 values, and nothing else
// ---------------------------------------------------------------------------

/** The stored values, in the order the Status dropdown renders them. */
export const PRODUCTION_STATUS_VALUES = ["in_progress", "closed"] as const;

export type ProductionStatusValue = (typeof PRODUCTION_STATUS_VALUES)[number];

/**
 * The one place the stored statuses become words a user reads.
 *
 * Stored values stay `in_progress` / `closed` everywhere - database, API, this
 * module's inputs. Only the rendering differs. There is deliberately no `open`
 * here: `project_activities` carries that third value for a different feature,
 * and Production Status is a two-state vocabulary until the business asks for
 * more.
 */
export const PRODUCTION_STATUS_LABEL: Record<ProductionStatusValue, string> = {
  in_progress: "IN PROGRESS",
  closed: "CLOSED",
};

/** Narrow whatever the API returned to a status the UI knows, else null. */
export function resolveProductionStatus(
  raw: string | null | undefined,
): ProductionStatusValue | null {
  return raw === "in_progress" || raw === "closed" ? raw : null;
}

/**
 * Display text for a stored status. A value from a newer backend renders as
 * itself rather than blanking the cell - an unknown status is information, not
 * a reason to show nothing.
 */
export function productionStatusLabel(raw: string | null | undefined): string {
  const known = resolveProductionStatus(raw);
  if (known) return PRODUCTION_STATUS_LABEL[known];
  return raw ? raw : VALUE_UNAVAILABLE;
}

// ---------------------------------------------------------------------------
// Counts
// ---------------------------------------------------------------------------

/**
 * Stands in for a value that is absent. A plain hyphen, never an empty string:
 * a blank cell reads as "this column does not exist for this row", which is the
 * confusion a visible placeholder avoids.
 */
export const VALUE_UNAVAILABLE = "-";

/**
 * The four count units, in the order the form's boxes and the table's columns
 * render them. TAG / DOC / SPARES / CRS are four independent values and are
 * never summed, averaged or collapsed into one "count" - not here, and not in
 * the backend column layout this mirrors.
 */
export const COUNT_UNITS = [
  { key: "tag_count", label: "TAG" },
  { key: "doc_count", label: "DOC" },
  { key: "spares_count", label: "SPARES" },
  { key: "crs_count", label: "CRS" },
] as const;

export type CountKey = (typeof COUNT_UNITS)[number]["key"];

/**
 * A count for display. Zero renders as the placeholder rather than "0" because
 * on this screen a zero means "this unit was not part of the update" - the
 * backend stores an unused unit as 0 by contract (NOT NULL DEFAULT 0), so 0 and
 * "not entered" are the same fact here.
 */
export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return VALUE_UNAVAILABLE;
  if (!Number.isFinite(value) || value === 0) return VALUE_UNAVAILABLE;
  return String(Math.round(value));
}

// ---------------------------------------------------------------------------
// Dates
// ---------------------------------------------------------------------------

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
] as const;

/**
 * A plain calendar date ("2025-12-05") as "05 Dec 2025".
 *
 * Parsed from the digits, never through `new Date(...)`: a date-only string is
 * parsed as UTC midnight by the JS Date constructor, so any viewer west of
 * Greenwich would see the previous day. `completed_on` is a wall-clock business
 * date with no timezone attached, and it must read identically everywhere -
 * the same reasoning as `lib/format.ts::parseWallClock`.
 */
export function formatProductionDate(raw: string | null | undefined): string {
  if (!raw) return VALUE_UNAVAILABLE;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(raw);
  if (!m) return VALUE_UNAVAILABLE;
  const month = MONTHS[Number(m[2]) - 1];
  if (!month) return VALUE_UNAVAILABLE;
  return `${m[3]} ${month} ${m[1]}`;
}

// ---------------------------------------------------------------------------
// Project - read-only, from the project the page already has
// ---------------------------------------------------------------------------

/** The project fields the form's read-only Project line reads. */
export interface ProjectDisplaySource {
  code?: string | null;
  name?: string | null;
  planning_plant_code?: string | null;
}

/**
 * The read-only "Project" value on the form - "4716-LC25102900".
 *
 * The project's CODE: the identifier the Projects UI names a project by, and
 * what the business writes on a report. Falls back to the descriptive name only
 * if a project somehow has no code.
 *
 * Plant is deliberately NOT part of this. The plant shown on this form is the
 * Maintenance Plant the user selects for the update, which is its own field and
 * its own stored value - it is never spliced into the project line, and it is
 * never derived from the project's Planning Plant.
 */
export function formatProjectDisplay(
  project: ProjectDisplaySource | null | undefined,
): string {
  if (!project) return VALUE_UNAVAILABLE;
  const code = project.code?.trim();
  if (code) return code;
  return project.name?.trim() || VALUE_UNAVAILABLE;
}

/**
 * Which Maintenance Plants the form may offer, expressed the way the shared
 * plant-master hook wants it: the project's Planning Plant CODE, or undefined.
 *
 * This is the whole of the "available for THIS project" rule on the client. The
 * options themselves come from `useMaintenancePlantOptions(true, code, !!code)`
 * - the same hook, over the same `GET /plants/maintenance-plants` endpoint,
 * with the same `planning_plant_code` scoping the Project Edit page uses. No
 * second plant source exists, and the backend validates a submitted plant
 * against that identical scoped list.
 *
 * `undefined` means the project has no Planning Plant, so there are no
 * Maintenance Plants to offer at all. That is a normal state: the field is left
 * empty and the update saves without one.
 *
 * Lives here rather than inline in the component so the rule is coverable by
 * `node --test`, which cannot mount JSX.
 */
export function maintenancePlantScope(
  project: ProjectDisplaySource | null | undefined,
): string | undefined {
  const code = project?.planning_plant_code?.trim();
  return code ? code : undefined;
}

// ---------------------------------------------------------------------------
// Activities - who may submit for which
// ---------------------------------------------------------------------------

/** One activity's staffing on the project, as GET /activity-staffing returns it. */
export interface ActivityStaffingLike {
  activity_id: string;
  activity_code?: string | null;
  activity_name?: string | null;
  lead?: { employee_id: string } | null;
}

export interface ActivityOption {
  id: string;
  label: string;
}

/** Who is looking at the tab, in the terms the backend authorizes on. */
export interface ProductionStatusViewer {
  /** Role-level PM. Authorizes every project. */
  canManage: boolean;
  /** This viewer is THIS project's assigned Head. */
  isHead: boolean;
  /** The viewer's employee id, or null when they have no employee profile. */
  employeeId: string | null;
}

export function activityLabel(activity: ActivityStaffingLike): string {
  const name = activity.activity_name?.trim();
  if (name) return name;
  const code = activity.activity_code?.trim();
  return code || VALUE_UNAVAILABLE;
}

/**
 * Every activity that is valid for this project.
 *
 * Deliberately derived from the project's activity STAFFING rather than from a
 * new list: "valid for the project" has exactly one definition, and it is the
 * backend's - `_fetch_valid_activity` accepts an activity only when it has a
 * `project_activity_members` row on that project. Reading the same join here
 * means the dropdown can never offer something the POST would reject, and no
 * second activity catalogue exists to drift.
 */
export function projectActivityOptions(
  staffing: readonly ActivityStaffingLike[] | null | undefined,
): ActivityOption[] {
  return (staffing ?? []).map((a) => ({ id: a.activity_id, label: activityLabel(a) }));
}

/** True when the viewer leads at least one activity on this project. */
export function leadsAnyActivity(
  staffing: readonly ActivityStaffingLike[] | null | undefined,
  employeeId: string | null,
): boolean {
  if (!employeeId) return false;
  return (staffing ?? []).some((a) => a.lead?.employee_id === employeeId);
}

/**
 * The activities the viewer may POST an update for.
 *
 * Mirrors backend `authz.activity_staffing_authority`:
 *   PM or this project's Head -> "full", every activity on the project
 *   the assigned Lead of one activity -> "lead", that activity only
 *   anyone else -> nothing
 *
 * Hiding an activity is convenience, not the control: the POST re-resolves the
 * same authority server-side and answers 403 regardless of what this returns.
 */
export function submittableActivityOptions(
  staffing: readonly ActivityStaffingLike[] | null | undefined,
  viewer: ProductionStatusViewer,
): ActivityOption[] {
  const all = staffing ?? [];
  if (viewer.canManage || viewer.isHead) return projectActivityOptions(all);
  if (!viewer.employeeId) return [];
  return projectActivityOptions(
    all.filter((a) => a.lead?.employee_id === viewer.employeeId),
  );
}

// ---------------------------------------------------------------------------
// Rows
// ---------------------------------------------------------------------------

/** One production-status update, as the API returns it. */
export interface ProductionStatusRecordLike {
  id: string;
  revision: string;
  activity_id: string;
  activity_name?: string | null;
  activity_code?: string | null;
  status: string;
  tag_count: number;
  doc_count: number;
  spares_count: number;
  crs_count: number;
  completed_on?: string | null;
  remarks?: string | null;
  created_by_name?: string | null;
  created_at: string;
}

export interface ProductionStatusRow {
  key: string;
  revision: string;
  activityId: string;
  activity: string;
  status: string;
  /** The raw stored status, for the badge to colour without re-parsing a label. */
  statusValue: ProductionStatusValue | null;
  tag: string;
  doc: string;
  spares: string;
  crs: string;
  completedOn: string;
  /** Raw remarks - rendered with whitespace preserved, never trimmed to one line. */
  remarks: string | null;
  by: string;
  updated: string;
}

/**
 * Shown in the "By" column when the API sent no author name.
 *
 * Never a role word. The author is always a person; if the name is missing the
 * honest answer is that it is unknown, not "Activity Lead" - which is exactly
 * the substitution Phase 1 exists to prevent.
 */
export const AUTHOR_UNKNOWN = VALUE_UNAVAILABLE;

/**
 * Turn API records into table rows.
 *
 * `formatDateTime` is injected rather than imported so this module stays
 * dependency-free and the tests can pin an exact string instead of asserting
 * against the runner's locale.
 */
export function buildProductionStatusRows(
  records: readonly ProductionStatusRecordLike[] | null | undefined,
  formatDateTime: (iso: string) => string,
): ProductionStatusRow[] {
  return (records ?? []).map((r) => ({
    key: r.id,
    revision: r.revision,
    activityId: r.activity_id,
    activity: activityLabel(r),
    status: productionStatusLabel(r.status),
    statusValue: resolveProductionStatus(r.status),
    tag: formatCount(r.tag_count),
    doc: formatCount(r.doc_count),
    spares: formatCount(r.spares_count),
    crs: formatCount(r.crs_count),
    completedOn: formatProductionDate(r.completed_on),
    remarks: r.remarks && r.remarks.trim() !== "" ? r.remarks : null,
    by: r.created_by_name?.trim() || AUTHOR_UNKNOWN,
    updated: formatDateTime(r.created_at),
  }));
}

// ---------------------------------------------------------------------------
// History target - which trail a row's History button opens
// ---------------------------------------------------------------------------

/**
 * The one trail the history dialog reads: ONE revision of ONE activity.
 *
 * Both parts are always carried together. That pairing is what keeps REV-0 and
 * REV-1 of the same activity separate trails and MTL and FMTL separate trails -
 * the dialog sends both as filters, and the backend's `list_history` ANDs them,
 * so opening one can never render another's updates.
 */
export interface ProductionStatusHistoryTarget {
  activityId: string;
  /** Display only - the dialog title. Never sent to the API. */
  activityLabel: string;
  revision: string;
}

/**
 * The trail belonging to a current-status row.
 *
 * Derived from the row rather than from form state, so the History button on a
 * row always opens that row's own revision + activity even after the form above
 * has been changed to something else.
 */
export function historyTargetFor(
  row: Pick<ProductionStatusRow, "activityId" | "activity" | "revision">,
): ProductionStatusHistoryTarget {
  return {
    activityId: row.activityId,
    activityLabel: row.activity,
    revision: row.revision,
  };
}

// ---------------------------------------------------------------------------
// Save
// ---------------------------------------------------------------------------

/**
 * Is a save already under way?
 *
 * Both flags matter, and neither alone is enough to stop a double-click:
 *
 *   `isSubmitting` is react-hook-form's, set the moment `handleSubmit` runs and
 *   held across the async zod validation - the window BEFORE any request
 *   exists, which `isPending` cannot cover.
 *
 *   `isPending` is the mutation's, held from the POST going out until the
 *   response lands - the window AFTER validation, which `isSubmitting`
 *   technically also covers but only because the submit handler awaits the
 *   mutation; keeping it explicit means the guard survives that handler being
 *   changed.
 *
 * The Save button is disabled while this is true (`Button` disables on
 * `loading`), so the second click of a double-click has nothing to hit.
 *
 * This is deliberately NOT a uniqueness rule. Two INTENTIONAL updates with
 * identical values are legitimate history and must both be stored - see
 * `backend/tests/test_production_status.py::test_identical_updates_both_recorded`.
 * The only thing suppressed here is a second submission of the SAME click.
 */
export function isSaveInFlight(state: {
  isPending: boolean;
  isSubmitting: boolean;
}): boolean {
  return state.isPending || state.isSubmitting;
}

// ---------------------------------------------------------------------------
// Copy
// ---------------------------------------------------------------------------

export const NO_STATUS_TITLE = "No production status recorded yet";
export const NO_STATUS_HINT =
  "The first update you save appears here as the current status for its revision and activity.";

export const NO_HISTORY_TITLE = "No updates recorded";
export const NO_HISTORY_HINT =
  "Every saved update is kept, so this list fills up as the activity progresses.";

export const NO_ACTIVITIES_TITLE = "No activities to update";
export const NO_ACTIVITIES_HINT =
  "Production status is recorded against an activity you are staffed on. Ask the project Head to assign you to one.";

export const NO_PROJECT_ACTIVITIES_HINT =
  "This project has no activity staffing yet, so there is nothing to record production status against.";

/**
 * Turn a failed request into something a user can act on.
 *
 * Mirrors the tag-scope tab's `tagScopeErrorMessage`: the backend's own message
 * is preferred when it explains a business rule (422/403), and the generic
 * fallbacks cover the cases where it does not.
 */
export function productionStatusErrorMessage(
  status: number | null,
  message: string | null,
): string {
  if (status === 403) {
    return (
      message ??
      "You can only record production status for activities you manage."
    );
  }
  if (status === 404) return message ?? "This project or activity no longer exists.";
  if (status === 422 || status === 400) return message ?? "Please check the form and try again.";
  if (status === 0) return "Could not reach the server. Check your connection and try again.";
  return message ?? "Something went wrong. Please try again.";
}
