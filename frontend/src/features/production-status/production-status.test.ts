/**
 * Production Status UI logic — Phase 2.
 *
 * The repo's frontend harness is `node --test` over `src/**​/*.test.ts` (see
 * package.json `test:unit`): plain TypeScript, no jsdom / React Testing
 * Library. So these tests pin the pure module the components render from —
 * which activities a viewer may submit for, what every cell says, and how the
 * form body is built — rather than mounting the tab.
 *
 * The backend rules these mirror are covered independently in
 * backend/tests/test_production_status.py.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  activityLabel,
  AUTHOR_UNKNOWN,
  buildProductionStatusRows,
  COUNT_UNITS,
  formatCount,
  formatProductionDate,
  formatProjectPlant,
  leadsAnyActivity,
  PRODUCTION_STATUS_LABEL,
  PRODUCTION_STATUS_VALUES,
  productionStatusErrorMessage,
  productionStatusLabel,
  projectActivityOptions,
  resolveProductionStatus,
  submittableActivityOptions,
  VALUE_UNAVAILABLE,
  type ActivityStaffingLike,
  type ProductionStatusRecordLike,
} from "./production-status.ts";
import {
  EMPTY_PRODUCTION_STATUS_FORM,
  productionStatusFormSchema,
  resetAfterSave,
  toProductionStatusBody,
  type ProductionStatusFormValues,
} from "./schemas.ts";

// A deterministic stand-in for lib/format.ts's formatDateTime, so these tests
// assert on content instead of on the runner's locale.
const fmt = (iso: string) => `@${iso.slice(0, 10)}`;

const LEAD_EMP = "emp-santhosh";
const OTHER_EMP = "emp-other";

const TAG_ESTIMATION: ActivityStaffingLike = {
  activity_id: "act-tag",
  activity_code: "TAGEST",
  activity_name: "TAG ESTIMATION",
  lead: { employee_id: LEAD_EMP },
};
const MTL_PREPARATION: ActivityStaffingLike = {
  activity_id: "act-mtl",
  activity_code: "MTL",
  activity_name: "MTL PREPARATION",
  lead: { employee_id: OTHER_EMP },
};
const UNLED: ActivityStaffingLike = {
  activity_id: "act-doc",
  activity_code: "DOC",
  activity_name: "DOCUMENTATION",
  lead: null,
};
const STAFFING = [TAG_ESTIMATION, MTL_PREPARATION, UNLED];

function record(over: Partial<ProductionStatusRecordLike> = {}): ProductionStatusRecordLike {
  return {
    id: "rec-1",
    revision: "REV-0",
    activity_id: "act-tag",
    activity_name: "TAG ESTIMATION",
    activity_code: "TAGEST",
    status: "in_progress",
    tag_count: 180,
    doc_count: 0,
    spares_count: 0,
    crs_count: 0,
    completed_on: null,
    remarks: null,
    created_by_name: "Santhosh Kumar",
    created_at: "2025-12-01T10:15:00+05:30",
    ...over,
  };
}

// ---------------------------------------------------------------------------
// 1. Status vocabulary — the Phase 1 values, and no second one
// ---------------------------------------------------------------------------

test("the status vocabulary is exactly the two Phase 1 values", () => {
  assert.deepEqual([...PRODUCTION_STATUS_VALUES], ["in_progress", "closed"]);
  // No third value leaks in from project_activities' open/in_progress/closed.
  assert.equal(PRODUCTION_STATUS_VALUES.includes("open" as never), false);
});

test("stored values render as user-friendly labels", () => {
  assert.equal(PRODUCTION_STATUS_LABEL.in_progress, "IN PROGRESS");
  assert.equal(PRODUCTION_STATUS_LABEL.closed, "CLOSED");
  assert.equal(productionStatusLabel("in_progress"), "IN PROGRESS");
  assert.equal(productionStatusLabel("closed"), "CLOSED");
});

test("an unknown status renders as itself rather than blanking the cell", () => {
  assert.equal(resolveProductionStatus("open"), null);
  assert.equal(resolveProductionStatus(null), null);
  assert.equal(productionStatusLabel("open"), "open");
  assert.equal(productionStatusLabel(null), VALUE_UNAVAILABLE);
});

// ---------------------------------------------------------------------------
// 2. Counts stay four independent values
// ---------------------------------------------------------------------------

test("the Count section is exactly TAG / DOC / SPARES / CRS, in order", () => {
  assert.deepEqual(
    COUNT_UNITS.map((u) => u.label),
    ["TAG", "DOC", "SPARES", "CRS"],
  );
  assert.deepEqual(
    COUNT_UNITS.map((u) => u.key),
    ["tag_count", "doc_count", "spares_count", "crs_count"],
  );
});

test("counts render independently and never combine", () => {
  const rows = buildProductionStatusRows(
    [record({ tag_count: 225, doc_count: 14, spares_count: 3, crs_count: 9 })],
    fmt,
  );
  assert.deepEqual(
    [rows[0].tag, rows[0].doc, rows[0].spares, rows[0].crs],
    ["225", "14", "3", "9"],
  );
});

test("an unused unit shows the placeholder, not a zero", () => {
  assert.equal(formatCount(0), VALUE_UNAVAILABLE);
  assert.equal(formatCount(null), VALUE_UNAVAILABLE);
  assert.equal(formatCount(undefined), VALUE_UNAVAILABLE);
  assert.equal(formatCount(225), "225");
});

// ---------------------------------------------------------------------------
// 3. Activity options — valid for the project, submittable by the viewer
// ---------------------------------------------------------------------------

test("the activity list is the project's staffed activities and nothing else", () => {
  // Same join the backend's _fetch_valid_activity accepts against, so the
  // dropdown can never offer something the POST would reject.
  assert.deepEqual(
    projectActivityOptions(STAFFING).map((o) => o.id),
    ["act-tag", "act-mtl", "act-doc"],
  );
  assert.deepEqual(projectActivityOptions([]), []);
  assert.deepEqual(projectActivityOptions(undefined), []);
});

test("an activity is labelled by name, falling back to its code", () => {
  assert.equal(activityLabel(TAG_ESTIMATION), "TAG ESTIMATION");
  assert.equal(activityLabel({ activity_id: "x", activity_code: "FMTL" }), "FMTL");
  assert.equal(activityLabel({ activity_id: "x" }), VALUE_UNAVAILABLE);
});

test("a PM may submit for every activity on the project", () => {
  const options = submittableActivityOptions(STAFFING, {
    canManage: true,
    isHead: false,
    employeeId: null,
  });
  assert.deepEqual(options.map((o) => o.id), ["act-tag", "act-mtl", "act-doc"]);
});

test("the project Head may submit for every activity on their project", () => {
  const options = submittableActivityOptions(STAFFING, {
    canManage: false,
    isHead: true,
    employeeId: "emp-head",
  });
  assert.deepEqual(options.map((o) => o.id), ["act-tag", "act-mtl", "act-doc"]);
});

test("an Activity Lead may submit only for the activity they lead", () => {
  const options = submittableActivityOptions(STAFFING, {
    canManage: false,
    isHead: false,
    employeeId: LEAD_EMP,
  });
  assert.deepEqual(options.map((o) => o.id), ["act-tag"]);
  assert.deepEqual(options.map((o) => o.label), ["TAG ESTIMATION"]);
});

test("someone who leads nothing is offered nothing to submit", () => {
  for (const employeeId of ["emp-nobody", null]) {
    assert.deepEqual(
      submittableActivityOptions(STAFFING, {
        canManage: false,
        isHead: false,
        employeeId,
      }),
      [],
    );
  }
});

test("leadsAnyActivity decides tab visibility for a Lead", () => {
  assert.equal(leadsAnyActivity(STAFFING, LEAD_EMP), true);
  assert.equal(leadsAnyActivity(STAFFING, OTHER_EMP), true);
  assert.equal(leadsAnyActivity(STAFFING, "emp-nobody"), false);
  assert.equal(leadsAnyActivity(STAFFING, null), false);
  assert.equal(leadsAnyActivity([UNLED], LEAD_EMP), false);
  assert.equal(leadsAnyActivity(undefined, LEAD_EMP), false);
});

// ---------------------------------------------------------------------------
// 4. "By" is the real person
// ---------------------------------------------------------------------------

test("By shows the author's actual name from the API, never a role", () => {
  const rows = buildProductionStatusRows([record()], fmt);
  assert.equal(rows[0].by, "Santhosh Kumar");
  for (const role of ["Activity Lead", "Project Head", "PM"]) {
    assert.notEqual(rows[0].by, role);
  }
});

test("a missing author name reads as unknown, never as a role word", () => {
  const rows = buildProductionStatusRows(
    [record({ created_by_name: null }), record({ id: "rec-2", created_by_name: "   " })],
    fmt,
  );
  assert.equal(rows[0].by, AUTHOR_UNKNOWN);
  assert.equal(rows[1].by, AUTHOR_UNKNOWN);
});

// ---------------------------------------------------------------------------
// 5. Rows / dates / remarks
// ---------------------------------------------------------------------------

test("rows carry the revision and activity that identify their trail", () => {
  const rows = buildProductionStatusRows(
    [
      record({ id: "a", revision: "REV-0" }),
      record({ id: "b", revision: "REV-1", tag_count: 12 }),
    ],
    fmt,
  );
  assert.deepEqual(rows.map((r) => r.revision), ["REV-0", "REV-1"]);
  assert.deepEqual(rows.map((r) => r.activityId), ["act-tag", "act-tag"]);
  assert.deepEqual(rows.map((r) => r.key), ["a", "b"]);
  assert.equal(rows[0].updated, "@2025-12-01");
});

test("a completion date renders from its digits, with no timezone shift", () => {
  // new Date("2025-12-05") is UTC midnight, which reads as 04 Dec west of
  // Greenwich. A business date must read the same everywhere.
  assert.equal(formatProductionDate("2025-12-05"), "05 Dec 2025");
  assert.equal(formatProductionDate("2026-01-31"), "31 Jan 2026");
  assert.equal(formatProductionDate(null), VALUE_UNAVAILABLE);
  assert.equal(formatProductionDate("not-a-date"), VALUE_UNAVAILABLE);
});

test("remarks are preserved verbatim, line breaks included", () => {
  const rows = buildProductionStatusRows(
    [record({ remarks: "Line one\nLine two" }), record({ id: "r2", remarks: "   " })],
    fmt,
  );
  assert.equal(rows[0].remarks, "Line one\nLine two");
  // Whitespace-only is nothing to show; the cell renders its own placeholder.
  assert.equal(rows[1].remarks, null);
});

test("no row is dropped and nothing is recomputed", () => {
  const records = [
    record({ id: "1", status: "in_progress", tag_count: 100 }),
    record({ id: "2", status: "in_progress", tag_count: 180 }),
    record({ id: "3", status: "closed", tag_count: 225, completed_on: "2025-12-05" }),
  ];
  const rows = buildProductionStatusRows(records, fmt);
  assert.equal(rows.length, 3);
  assert.deepEqual(rows.map((r) => r.tag), ["100", "180", "225"]);
  assert.deepEqual(rows.map((r) => r.status), ["IN PROGRESS", "IN PROGRESS", "CLOSED"]);
  assert.equal(rows[2].completedOn, "05 Dec 2025");
  assert.deepEqual(buildProductionStatusRows(undefined, fmt), []);
});

// ---------------------------------------------------------------------------
// 6. Project / Plant is derived, never entered
// ---------------------------------------------------------------------------

test("Project / Plant is assembled from the project row", () => {
  assert.equal(
    formatProjectPlant({ code: "GC25100600", name: "X", maintenance_plant_code: "ABCD" }),
    "GC25100600 / ABCD",
  );
  // Maintenance Plant wins; the Planning Plant is the fallback.
  assert.equal(
    formatProjectPlant({ code: "GC25100600", planning_plant_code: "1200" }),
    "GC25100600 / 1200",
  );
  assert.equal(formatProjectPlant({ code: "GC25100600" }), "GC25100600");
  assert.equal(formatProjectPlant({ name: "Unnamed" }), "Unnamed");
  assert.equal(formatProjectPlant(null), VALUE_UNAVAILABLE);
});

// ---------------------------------------------------------------------------
// 7. The form body — what is submitted, and what is not
// ---------------------------------------------------------------------------

function values(over: Partial<ProductionStatusFormValues> = {}): ProductionStatusFormValues {
  return { ...EMPTY_PRODUCTION_STATUS_FORM, ...over };
}

test("the body carries only the nine fields the user entered", () => {
  const body = toProductionStatusBody(
    values({
      revision: "REV-0",
      activity_id: "act-tag",
      status: "closed",
      tag_count: "225",
      completed_on: "2025-12-05",
      remarks: "Closed after QC",
    }),
  );
  assert.deepEqual(Object.keys(body).sort(), [
    "activity_id",
    "completed_on",
    "crs_count",
    "doc_count",
    "remarks",
    "revision",
    "spares_count",
    "status",
    "tag_count",
  ]);
  // The project is the path and the author is the token — never the body.
  assert.equal("project_id" in body, false);
  assert.equal("created_by" in body, false);
});

test("a blank count is sent as 0, matching the API's unused-unit contract", () => {
  const body = toProductionStatusBody(
    values({ revision: "REV-0", activity_id: "a", tag_count: "225" }),
  );
  assert.deepEqual(
    [body.tag_count, body.doc_count, body.spares_count, body.crs_count],
    [225, 0, 0, 0],
  );
});

test("an empty completion date and empty remarks are sent as null", () => {
  const body = toProductionStatusBody(values({ revision: "REV-0", activity_id: "a" }));
  assert.equal(body.completed_on, null);
  assert.equal(body.remarks, null);
});

test("revision is trimmed before it is sent", () => {
  const body = toProductionStatusBody(
    values({ revision: "  REV-1  ", activity_id: "a" }),
  );
  assert.equal(body.revision, "REV-1");
});

test("nothing pre-fills today's date or a starting count", () => {
  assert.equal(EMPTY_PRODUCTION_STATUS_FORM.completed_on, "");
  assert.equal(EMPTY_PRODUCTION_STATUS_FORM.tag_count, "");
  assert.equal(EMPTY_PRODUCTION_STATUS_FORM.status, "in_progress");
});

// ---------------------------------------------------------------------------
// 8. Form validation
// ---------------------------------------------------------------------------

test("revision is required and whitespace is not a revision", () => {
  assert.equal(productionStatusFormSchema.safeParse(values({ activity_id: "a" })).success, false);
  assert.equal(
    productionStatusFormSchema.safeParse(values({ revision: "   ", activity_id: "a" })).success,
    false,
  );
  assert.equal(
    productionStatusFormSchema.safeParse(values({ revision: "REV-0", activity_id: "a" })).success,
    true,
  );
});

test("an activity must be selected", () => {
  assert.equal(productionStatusFormSchema.safeParse(values({ revision: "REV-0" })).success, false);
});

test("only the two Phase 1 statuses validate", () => {
  for (const status of ["in_progress", "closed"]) {
    assert.equal(
      productionStatusFormSchema.safeParse(
        values({ revision: "REV-0", activity_id: "a", status: status as never }),
      ).success,
      true,
    );
  }
  assert.equal(
    productionStatusFormSchema.safeParse(
      values({ revision: "REV-0", activity_id: "a", status: "open" as never }),
    ).success,
    false,
  );
});

test("a completion date is optional for BOTH statuses", () => {
  // The backend accepts either, so the UI must not invent a stricter rule.
  for (const status of ["in_progress", "closed"] as const) {
    assert.equal(
      productionStatusFormSchema.safeParse(
        values({ revision: "REV-0", activity_id: "a", status, completed_on: "" }),
      ).success,
      true,
    );
    assert.equal(
      productionStatusFormSchema.safeParse(
        values({ revision: "REV-0", activity_id: "a", status, completed_on: "2025-12-05" }),
      ).success,
      true,
    );
  }
});

// ---------------------------------------------------------------------------
// 9. Append-only: what the form keeps after a save
// ---------------------------------------------------------------------------

test("saving keeps the revision/activity/status and clears this update's figures", () => {
  const next = resetAfterSave(
    values({
      revision: "  REV-0  ",
      activity_id: "act-tag",
      status: "closed",
      tag_count: "225",
      doc_count: "14",
      spares_count: "3",
      crs_count: "9",
      completed_on: "2025-12-05",
      remarks: "Closed after QC",
    }),
  );
  assert.equal(next.revision, "REV-0");
  assert.equal(next.activity_id, "act-tag");
  assert.equal(next.status, "closed");
  // Nothing about the update just saved can leak into the next one.
  assert.deepEqual(
    [next.tag_count, next.doc_count, next.spares_count, next.crs_count],
    ["", "", "", ""],
  );
  assert.equal(next.completed_on, "");
  assert.equal(next.remarks, "");
});

// ---------------------------------------------------------------------------
// 10. Error copy
// ---------------------------------------------------------------------------

test("errors read as something the user can act on", () => {
  assert.match(productionStatusErrorMessage(403, null), /activities you manage/i);
  assert.equal(productionStatusErrorMessage(403, "Not yours."), "Not yours.");
  assert.match(productionStatusErrorMessage(404, null), /no longer exists/i);
  assert.equal(
    productionStatusErrorMessage(422, "That activity is not part of this project."),
    "That activity is not part of this project.",
  );
  assert.match(productionStatusErrorMessage(0, null), /reach the server/i);
  assert.match(productionStatusErrorMessage(500, null), /went wrong/i);
});
