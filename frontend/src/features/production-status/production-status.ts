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

/**
 * The name to show for an activity.
 *
 * Takes only the two fields it reads, so it serves a staffing row and a
 * production status record alike - the API already resolves `activity_name` for
 * both an Activity Master activity and a typed one, so neither caller has to
 * know which kind it holds.
 */
export function activityLabel(activity: {
  activity_name?: string | null;
  activity_code?: string | null;
}): string {
  const name = activity.activity_name?.trim();
  if (name) return name;
  const code = activity.activity_code?.trim();
  return code || VALUE_UNAVAILABLE;
}

/**
 * The activities this project is STAFFED for.
 *
 * Still exactly the `project_activity_members` join, and still what an Activity
 * Lead's own options are drawn from. It is no longer the Head's list: see
 * `submittableActivityOptions`.
 */
export function projectActivityOptions(
  staffing: readonly ActivityStaffingLike[] | null | undefined,
): ActivityOption[] {
  return (staffing ?? []).map((a) => ({ id: a.activity_id, label: activityLabel(a) }));
}

/** One Activity Master activity, as GET /activity-master/activities returns it. */
export interface ActivityMasterLike {
  id: string;
  code?: string | null;
  name?: string | null;
  level?: string | null;
  is_active?: boolean | null;
}

/**
 * Every activity in Activity Master, as dropdown options.
 *
 * The Head's list. Top-level Activities only and active ones only - a
 * sub-activity is refused by the backend (`_fetch_valid_activity`), and an
 * inactive activity is retired master data that should not be offered for new
 * work. Sorted by the name actually shown, so the list reads alphabetically
 * however the master data happens to be ordered.
 */
export function activityMasterOptions(
  activities: readonly ActivityMasterLike[] | null | undefined,
): ActivityOption[] {
  return (activities ?? [])
    .filter((a) => a.is_active !== false && (a.level ?? "activity") === "activity")
    .map((a) => ({
      id: a.id,
      label: (a.name ?? "").trim() || (a.code ?? "").trim() || VALUE_UNAVAILABLE,
    }))
    .sort((a, b) => a.label.localeCompare(b.label));
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
 * May this viewer record production status at all?
 *
 * Mirrors backend `_record_authority`:
 *   this project's Head          yes - every activity, and may type a new one
 *   the Lead of an activity here yes - that activity only
 *   the project_manager          NO. Read-only, deliberately.
 *
 * The PM exclusion is the point, not an oversight: production status is a claim
 * about work that was done, made by the people who did it. The PM reads the tab
 * and reads the cumulative report nobody else can.
 *
 * Hiding the form is convenience, not the control - the POST re-resolves the
 * same rule and answers 403 regardless of what this returns.
 */
export function canRecordProductionStatus(
  staffing: readonly ActivityStaffingLike[] | null | undefined,
  viewer: ProductionStatusViewer,
): boolean {
  if (viewer.isHead) return true;
  return leadsAnyActivity(staffing, viewer.employeeId);
}

/** May this viewer type an activity that is not in Activity Master? Head only. */
export function canTypeNewActivity(viewer: ProductionStatusViewer): boolean {
  return viewer.isHead;
}

// ---------------------------------------------------------------------------
// A typed activity, inside a dropdown that selects by id
// ---------------------------------------------------------------------------

/**
 * Marks a dropdown selection as a name the user TYPED rather than an id they
 * picked.
 *
 * The activity control is one Combobox with one string value, and that value
 * has to be able to say either "this Activity Master row" or "these words".
 * Prefixing is how it says the second without a second form field to keep in
 * step - `parseActivitySelection` turns it back into the two fields the API
 * actually takes.
 *
 * A colon cannot appear in a UUID, so a real id can never be mistaken for a
 * typed one however the two are mixed.
 */
export const TYPED_ACTIVITY_PREFIX = "new:";

/** The dropdown value standing for a typed activity name. */
export function typedActivityValue(label: string): string {
  return `${TYPED_ACTIVITY_PREFIX}${label.trim()}`;
}

/** True when this selection is a typed name rather than an Activity Master id. */
export function isTypedActivity(value: string | null | undefined): boolean {
  return (value ?? "").startsWith(TYPED_ACTIVITY_PREFIX);
}

/**
 * One dropdown value -> the two fields the API takes, exactly one of them set.
 *
 * The same split the backend enforces (`_exactly_one_activity`), done once
 * here, so the form never has to reason about which kind of activity it holds.
 * An empty selection yields two nulls and the form's own required-check is what
 * catches it.
 */
export function parseActivitySelection(value: string | null | undefined): {
  activity_id: string | null;
  activity_label: string | null;
} {
  const raw = (value ?? "").trim();
  if (!raw) return { activity_id: null, activity_label: null };
  if (isTypedActivity(raw)) {
    const label = raw.slice(TYPED_ACTIVITY_PREFIX.length).trim();
    return label
      ? { activity_id: null, activity_label: label }
      : { activity_id: null, activity_label: null };
  }
  return { activity_id: raw, activity_label: null };
}

/**
 * The options list with the current typed activity included.
 *
 * A typed name is not in Activity Master, so without this the Combobox would
 * have nothing to render for its own selected value and the field would look
 * empty right after the user typed into it. Appended, never merged into the
 * master list, and only while it is the selection.
 */
export function withTypedActivityOption(
  options: readonly ActivityOption[],
  value: string | null | undefined,
): ActivityOption[] {
  if (!isTypedActivity(value)) return [...options];
  const { activity_label } = parseActivitySelection(value);
  if (!activity_label) return [...options];
  return [...options, { id: value as string, label: activity_label }];
}

/**
 * The activities the viewer may POST an update for.
 *
 *   the Head   EVERY activity in Activity Master - not just the ones this
 *              project is staffed for. The Head owns the project's whole
 *              output and reports on activities nobody may be formally staffed
 *              on yet; requiring staffing left a project with none unable to
 *              record anything at all.
 *   a Lead     the activities they lead ON THIS PROJECT, from its staffing.
 *              Their authority is over the activity they were given, and that
 *              is unchanged.
 *   the PM     none - they do not get the form.
 *
 * Two sources on purpose, because the two rules genuinely ask different
 * questions. Both mirror the backend, which validates whatever is submitted
 * either way.
 */
export function submittableActivityOptions(
  staffing: readonly ActivityStaffingLike[] | null | undefined,
  activityMaster: readonly ActivityMasterLike[] | null | undefined,
  viewer: ProductionStatusViewer,
): ActivityOption[] {
  if (viewer.isHead) return activityMasterOptions(activityMaster);
  if (!viewer.employeeId) return [];
  return projectActivityOptions(
    (staffing ?? []).filter((a) => a.lead?.employee_id === viewer.employeeId),
  );
}

// ---------------------------------------------------------------------------
// Rows
// ---------------------------------------------------------------------------

/** One production-status update, as the API returns it. */
export interface ProductionStatusRecordLike {
  id: string;
  revision: string;
  /** Null when the activity was typed rather than chosen (migration 0072). */
  activity_id?: string | null;
  /** Resolved server-side from whichever way the activity was named. */
  activity_name?: string | null;
  activity_code?: string | null;
  /** The typed name itself, null for an Activity Master activity. */
  activity_label?: string | null;
  status: string;
  tag_count: number;
  doc_count: number;
  spares_count: number;
  crs_count: number;
  completed_on?: string | null;
  remarks?: string | null;
  /** The AUTHOR's users.id - the record's ownership, and the only thing the
   *  Delete control is decided from. Never an employee id and never a role. */
  created_by?: string | null;
  created_by_name?: string | null;
  created_at: string;
}

export interface ProductionStatusRow {
  key: string;
  revision: string;
  /** Null when the activity was typed - see `typedActivity`. */
  activityId: string | null;
  /** The typed activity name, null for an Activity Master activity. Together
   *  with `activityId` this is what identifies the row's history trail. */
  typedActivity: string | null;
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
  /** The author's users.id, for `canDeleteProductionStatusRow`. Distinct from
   *  `by`, which is a display name and can legitimately repeat. */
  createdBy: string | null;
  updated: string;
}

/**
 * May this viewer delete this record?
 *
 * They recorded it. That is the whole rule, and it is deliberately not widened
 * by role: a Head cannot delete a Lead's record, a Lead cannot delete another
 * Lead's, and the PM - read-only on this tab - cannot delete anyone's.
 *
 * Comparing users.id, the same identity the backend stamped into `created_by`
 * from the token. Never the author's NAME: two people can share one, and a name
 * is display data. A missing id on either side is "no", so an unknown author is
 * never deletable by accident.
 *
 * Hiding the button is convenience only - `DELETE /production-status/{id}`
 * re-resolves this same comparison server-side and answers 403 regardless.
 */
export function canDeleteProductionStatusRow(
  row: Pick<ProductionStatusRow, "createdBy">,
  viewerUserId: string | null | undefined,
): boolean {
  return !!row.createdBy && !!viewerUserId && row.createdBy === viewerUserId;
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
    activityId: r.activity_id ?? null,
    typedActivity: r.activity_label?.trim() || null,
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
    createdBy: r.created_by ?? null,
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
  /** The Activity Master id to filter on, null for a typed activity. */
  activityId: string | null;
  /** The typed name to filter on, null for an Activity Master activity.
   *  Exactly one of these two is set, mirroring the record itself. */
  typedActivity: string | null;
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
  row: Pick<
    ProductionStatusRow,
    "activityId" | "typedActivity" | "activity" | "revision"
  >,
): ProductionStatusHistoryTarget {
  return {
    activityId: row.activityId,
    typedActivity: row.typedActivity,
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
  "Production status is recorded against an activity you lead. Ask the project Head to assign you to one.";

// The Head sees every Activity Master activity, so an empty list here means the
// master data itself is empty - and they can type one anyway.
export const NO_MASTER_ACTIVITIES_HINT =
  "No activities exist in Activity Master yet. You can still type the activity you want to record against.";

// The PM: read-only on this tab by design.
export const READ_ONLY_TITLE = "Production status is recorded by the project team";
export const READ_ONLY_HINT =
  "The project Head and its activity leads record these updates. You can read every project's current status here, and download the cumulative report from the Projects page.";

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
