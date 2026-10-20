import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

// Relative .ts import: the host-Node harness resolves no `@/` alias for values.
import {
  COMP_OFF_STATUSES,
  COMP_OFF_STATUS_LABEL,
  COMP_OFF_STATUS_VARIANT,
  COMP_OFF_TAB_HREF,
  addDaysIso,
  businessToday,
  canCancel,
  canDecide,
  compOffDetailHref,
  compOffErrorMessage,
  compOffView,
  decidedByLabel,
  formatShortDate,
  hasErrors,
  rejectionReasonError,
  validateCompOffDates,
  type CompOffRequest,
} from "./types.ts";

const TODAY = "2027-03-10";
const EMP = { role: "employee", employeeId: "emp-1" };
const PM = { role: "project_manager", employeeId: "pm-1" };

function req(over: Partial<CompOffRequest> = {}): CompOffRequest {
  return {
    id: "r1",
    employee_id: "emp-1",
    employee_name: "Ravi K",
    worked_date: "2027-03-07",
    off_date: "2027-03-15",
    reason: null,
    status: "pending",
    manager_id: null,
    manager_name: null,
    manager_comment: null,
    reviewed_at: null,
    created_at: "2027-03-08T10:00:00Z",
    updated_at: "2027-03-08T10:00:00Z",
    ...over,
  };
}

// -- the form's date rules ----------------------------------------------------

test("a valid pair of dates has no errors", () => {
  assert.equal(hasErrors(validateCompOffDates("2027-03-07", "2027-03-15", TODAY)), false);
});

test("both dates are required", () => {
  const e = validateCompOffDates("", "", TODAY);
  assert.ok(e.worked_date && e.off_date);
});

test("the day worked cannot be in the future; today is allowed", () => {
  assert.ok(validateCompOffDates("2027-03-11", "2027-03-15", TODAY).worked_date);
  assert.equal(validateCompOffDates(TODAY, "2027-03-15", TODAY).worked_date, undefined);
});

test("the day off must be strictly after today", () => {
  assert.ok(validateCompOffDates("2027-03-07", TODAY, TODAY).off_date);
  assert.ok(validateCompOffDates("2027-03-07", "2027-03-01", TODAY).off_date);
  assert.equal(validateCompOffDates("2027-03-07", "2027-03-11", TODAY).off_date, undefined);
});

test("the two dates must differ", () => {
  assert.ok(validateCompOffDates("2027-03-15", "2027-03-15", "2027-03-20").off_date);
});

test("no overtime-hours field or threshold exists in the form rules", () => {
  // The rules take exactly two dates and today - nothing about hours.
  assert.equal(validateCompOffDates.length, 3);
});

test("addDaysIso crosses month ends without a timezone shift", () => {
  assert.equal(addDaysIso("2027-02-28", 1), "2027-03-01");
  assert.equal(addDaysIso("2027-03-10", 1), "2027-03-11");
});

test("businessToday is the Chennai date", () => {
  // 20:00 UTC on the 9th is already the 10th in Asia/Kolkata.
  assert.equal(businessToday(new Date("2027-03-09T20:00:00Z")), "2027-03-10");
});

test("formatShortDate reads dates and timestamps", () => {
  assert.equal(formatShortDate("2027-03-07"), "07 Mar 2027");
  assert.equal(formatShortDate("2027-03-08T10:00:00Z"), "08 Mar 2027");
  assert.equal(formatShortDate(null), "-");
});

// -- rejection ----------------------------------------------------------------

test("rejection needs a non-blank reason", () => {
  assert.ok(rejectionReasonError(""));
  assert.ok(rejectionReasonError("   "));
  assert.equal(rejectionReasonError("Not site work"), null);
});

// -- statuses -----------------------------------------------------------------

test("every backend status has a label and a badge colour", () => {
  assert.deepEqual(COMP_OFF_STATUSES, ["pending", "approved", "rejected", "cancelled"]);
  for (const s of COMP_OFF_STATUSES) {
    assert.ok(COMP_OFF_STATUS_LABEL[s]);
    assert.ok(COMP_OFF_STATUS_VARIANT[s]);
  }
  assert.equal(COMP_OFF_STATUS_VARIANT.approved, "success");
  assert.equal(COMP_OFF_STATUS_VARIANT.rejected, "danger");
});

// -- who sees what ------------------------------------------------------------

test("an employee requests and never reviews", () => {
  assert.deepEqual(compOffView(EMP), { canRequest: true, canReview: false });
});

test("a Project Head is an employee here - no review access", () => {
  // Head-ness is per project and the role stays "employee"; comp off has no
  // Head routing, so nothing about being a Head grants a decision.
  assert.equal(compOffView({ role: "employee", employeeId: "head-1" }).canReview, false);
});

test("a project manager reviews", () => {
  assert.equal(compOffView(PM).canReview, true);
});

test("no employee profile means no request form", () => {
  assert.equal(compOffView({ role: "employee", employeeId: null }).canRequest, false);
});

test("decision controls only for a PM, only on someone else's pending request", () => {
  assert.equal(canDecide(req(), PM), true);
  assert.equal(canDecide(req(), EMP), false);
  assert.equal(canDecide(req({ employee_id: "pm-1" }), PM), false);
  for (const status of ["approved", "rejected", "cancelled"] as const) {
    assert.equal(canDecide(req({ status }), PM), false);
  }
});

test("cancel only on the author's own pending request - approved is final", () => {
  assert.equal(canCancel(req(), EMP), true);
  assert.equal(canCancel(req({ status: "approved" }), EMP), false);
  assert.equal(canCancel(req({ employee_id: "someone-else" }), EMP), false);
  assert.equal(canCancel(req(), PM), false);
});

// -- error handling -----------------------------------------------------------

test("a 409 tells the user to refresh and never reads as success", () => {
  const msg = compOffErrorMessage(409, "This comp off request is already approved.", "approve");
  assert.match(msg, /already approved/);
  assert.match(msg, /Refresh/);
  assert.doesNotMatch(msg, /success/i);
});

test("a 422 shows the server's business-rule message as-is", () => {
  const server = "No submitted work report with project activities exists for 7 March 2027.";
  assert.equal(compOffErrorMessage(422, server, "submit"), server);
});

test("a 5xx or network failure never shows server text", () => {
  const msg = compOffErrorMessage(500, "Traceback (most recent call last)", "approve the request");
  assert.doesNotMatch(msg, /Traceback/);
  assert.match(msg, /try again/);
  assert.match(compOffErrorMessage(undefined, undefined, "submit"), /try again/);
});

// -- placement: a tab, not a page ---------------------------------------------

const SRC = join(fileURLToPath(new URL(".", import.meta.url)), "..", "..");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? [path, ...walk(path)] : [];
  });
}

test("the only Comp Off route is the request detail under /attendance", () => {
  // Like /attendance/leave/[id]: a child of the Attendance page, never a page of
  // its own. The list lives on the Attendance page's Comp Off tab.
  const app = join(SRC, "app");
  const routes = walk(app)
    .filter((d) => /comp[-_]?off/i.test(d))
    .map((d) => d.slice(app.length + 1).replace(/\\/g, "/"));
  assert.deepEqual(routes.sort(), [
    "(app)/attendance/comp-off",
    "(app)/attendance/comp-off/[id]",
  ]);
  assert.equal(existsSync(join(app, "(app)", "attendance", "comp-off", "page.tsx")), false);
  assert.equal(
    existsSync(join(app, "(app)", "attendance", "comp-off", "[id]", "page.tsx")),
    true,
  );
});

test("the detail page is addressed under /attendance and returns to the tab", () => {
  assert.equal(compOffDetailHref("r1"), "/attendance/comp-off/r1");
  assert.equal(COMP_OFF_TAB_HREF, "/attendance?tab=comp-off");
});

test("only a decided request names who decided it", () => {
  assert.equal(decidedByLabel("approved"), "Approved by");
  assert.equal(decidedByLabel("rejected"), "Rejected by");
  assert.equal(decidedByLabel("pending"), null);
  assert.equal(decidedByLabel("cancelled"), null);
});

test("the sidebar has no Comp Off item", () => {
  const sidebar = join(SRC, "components", "shell", "sidebar.tsx");
  assert.ok(existsSync(sidebar));
  assert.doesNotMatch(readFileSync(sidebar, "utf8"), /comp[-_ ]?off/i);
});

test("the API client never sends an employee id", () => {
  // The server takes the requester from the session and scopes a non-manager's
  // list to their own requests; the browser must not try to name anyone.
  const apiSource = readFileSync(join(SRC, "features", "comp-off", "api.ts"), "utf8");
  assert.doesNotMatch(apiSource, /employee_id/);
});
