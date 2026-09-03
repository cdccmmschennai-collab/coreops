/**
 * The "All Requests" tab - leave AND permission history in one table.
 *
 * Phase 4F renamed the "All leave" tab and put permission requests in it. The
 * tab's URL key is still `queue=all` and its filter parameters are still `ls` /
 * `lf` / `lt` / `lo`, deliberately: an existing bookmark, a Back navigation and
 * the round trip through a detail page all keep working, because only the label
 * and the rows changed.
 *
 * WHY THE ROWS COME FROM ONE ENDPOINT
 * ===================================
 * `GET /api/v1/all-requests` returns both kinds already scoped, filtered, sorted
 * and paged - see `backend/app/modules/leave/all_requests.py`. Merging two paged
 * lists in the browser cannot be made exactly right (the second page of a merge
 * needs rows neither call fetched), and the failure mode is silently dropping
 * permission rows, which is the one thing this view must not do.
 *
 * WHAT LIVES HERE
 * ===============
 * The pure per-row decisions, kept out of the component so the host-Node unit
 * test can load them directly - the repo has no DOM test runner, so the way a
 * rule is made testable is to keep it out of the JSX. Every one of them defers
 * to the label map or helper the owning feature already has; nothing about
 * leave or permission is re-implemented here.
 *
 *     npm run test:unit
 */
import {
  LEAVE_CLASSIFICATION_LABEL,
  leaveDecisionActor,
  leaveDetailHref,
  type LeaveClassification,
  type LeaveStatus,
} from "./types.ts";
import {
  permissionDecisionActor,
  permissionDetailHref,
  type PermissionPeriod,
  type PermissionStatus,
} from "../permissions/types.ts";

/** Which kind of request a row is. Everything below branches on this and only
 *  on this - never on "does it have a period", which a pre-Phase-4C permission
 *  would fail. */
export type AllRequestKind = "leave" | "permission";

/** The five statuses BOTH kinds share, which is what makes one status filter and
 *  one badge column legal across a mixed table. Written out rather than derived
 *  as `LeaveStatus & PermissionStatus`: an intersection of two identical literal
 *  unions is not reliably assignable to either member, and this has to be usable
 *  as both. The two compile-time assignments below are what keep it honest - if
 *  either feature ever adds or renames a status, this file stops compiling. */
export type AllRequestStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "cancelled"
  | "cancellation_requested";

const _statusIsALeaveStatus: LeaveStatus = "pending" as AllRequestStatus;
const _statusIsAPermissionStatus: PermissionStatus = "pending" as AllRequestStatus;
void _statusIsALeaveStatus;
void _statusIsAPermissionStatus;

/** One row of `GET /all-requests`.
 *
 *  The kind-specific fields are null on the other kind. They are raw values, not
 *  display strings: the Type cell is composed here from the label map each
 *  feature already owns, so there is no third copy of either wording to drift. */
export interface AllRequest {
  id: string;
  kind: AllRequestKind;
  employee_id: string;
  /** Resolved by the backend, as on both source lists - `GET /employees` is
   *  RBAC-scoped and returns only their own row to a plain employee-role actor,
   *  which a Project Head still is. */
  employee_name: string | null;
  /** A leave's period. For a permission both are its single `permission_date`,
   *  which is what lets one date window filter both kinds. */
  from_date: string;
  to_date: string;
  status: AllRequestStatus;
  reason: string | null;
  /** The ACTUAL decision actor's employee id, stamped by whichever module owns
   *  the row when somebody clicked. Read through `allRequestActor`. */
  manager_id: string | null;
  manager_name: string | null;
  created_at: string;
  /** Leave only: Normal or Special, derived by the backend from the working-day
   *  count the approval actually charges. */
  classification: LeaveClassification | null;
  working_days: number | null;
  /** Permission only. `period` is null for a request filed before Phase 4C. */
  period: PermissionPeriod | null;
  duration_hours: number | null;
}

export interface AllRequestPage {
  items: AllRequest[];
  total: number;
  limit: number;
  offset: number;
}

export interface AllRequestListParams {
  employee_id?: string;
  status?: AllRequestStatus | "";
  from?: string;
  to?: string;
  limit: number;
  offset: number;
  /** Drop the caller's own requests - what a Project Head's reused panel passes,
   *  since nobody reviews their own. Enforced server-side either way. */
  exclude_self?: boolean;
}

/**
 * The COMPACT permission wording, used by the Type cell of this table and
 * nowhere else.
 *
 * The full wording - "Permission - 1st Half - 2 Hours", from
 * `PERMISSION_PERIOD_LABEL` - is a two-line cell at this column width, which
 * doubled the height of every permission row. The fix is a shorter label, NOT a
 * smaller font: the table's typography is the system's and stays untouched.
 *
 * Only the presentation is short. The stored `period` value, the request
 * dialog, the detail page, Permission History and the emails all keep the full
 * authoritative wording - this is deliberately a separate map rather than a
 * transformation of that one, because the two are allowed to differ and only
 * this table may use the short form.
 *
 * `Record<PermissionPeriod, ...>` is what keeps it honest: adding a fifth
 * option to `PERMISSION_PERIOD_OPTIONS` stops this file compiling until the
 * compact label for it is written too.
 *
 * The separator is a MIDDLE DOT (U+00B7), not an em or en dash - the house rule
 * this repo enforces is against dashes, and a dot is what keeps three fields
 * legible in a cell this narrow.
 */
const COMPACT_PERMISSION_PERIOD_LABEL: Record<PermissionPeriod, string> = {
  first_half_1h: "P · 1st Half · 1 hr",
  second_half_1h: "P · 2nd Half · 1 hr",
  first_half_2h: "P · 1st Half · 2 hrs",
  second_half_2h: "P · 2nd Half · 2 hrs",
};

/**
 * The Type cell.
 *
 *   leave       "Normal" / "Special"     - unchanged from All leave
 *   permission  "P · 1st Half · 2 hrs"   - the compact form above
 *
 * The leave half is exactly what the tab rendered before, so no existing leave
 * row changes. The permission half still prefixes the kind - "P" - because in a
 * mixed table the status badge does not tell a reader which sort of absence
 * they are looking at, and still names the SELECTED OPTION rather than a bare
 * hour count. A request filed before that option existed has no half on record
 * and none that could be safely guessed, so it falls back to the kind and the
 * hours alone.
 */
export function allRequestTypeLabel(row: AllRequest): string {
  if (row.kind === "leave") {
    return row.classification ? LEAVE_CLASSIFICATION_LABEL[row.classification] : "Leave";
  }
  if (row.period) return COMPACT_PERMISSION_PERIOD_LABEL[row.period];
  const hours = row.duration_hours ?? 0;
  return `P · ${hours}${hours === 1 ? "hr" : "hrs"}`;
}

/**
 * The "By" cell: who ruled on this row, or null for a dash.
 *
 * Each kind goes through ITS OWN feature's rule rather than a third one written
 * here, so the column cannot disagree with the detail page it links to. The two
 * rules happen to agree - approved and rejected name the actor, everything else
 * shows nothing - and that agreement is what makes the mixed column readable
 * without the reader having to know which kind a row is.
 *
 * A cancelled row of either kind is blank on purpose: its `manager_id` is the
 * former APPROVER, the cancellation was a different act, and no column records
 * who performed it. Naming the approver there would name the wrong person.
 */
export function allRequestActor(row: AllRequest): string | null {
  return row.kind === "leave"
    ? leaveDecisionActor({ status: row.status, manager_name: row.manager_name })
    : permissionDecisionActor({ status: row.status, manager_name: row.manager_name });
}

/**
 * Where a row opens, carrying the list it was clicked FROM.
 *
 * A leave row opens the existing Leave Detail page and a permission row the
 * existing Permission Detail page - the same two pages their own queues open,
 * so no third detail layout exists to keep in step. Both hrefs are built by the
 * feature's own helper, which round-trips `from` whole; neither back link is
 * hardcoded here, so the reader returns to All Requests with its filters, its
 * page and (for a Project Head) its `view=team` intact.
 */
export function allRequestDetailHref(row: AllRequest, from?: string | null): string {
  return row.kind === "leave"
    ? leaveDetailHref(row.id, from)
    : permissionDetailHref(row.id, from);
}
