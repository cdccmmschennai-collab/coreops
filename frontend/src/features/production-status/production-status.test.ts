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

import { productionStatusKeys } from "./keys.ts";
import {
  activityLabel,
  AUTHOR_UNKNOWN,
  buildProductionStatusRows,
  canDeleteProductionStatusRow,
  COUNT_UNITS,
  formatCount,
  formatProductionDate,
  formatProjectDisplay,
  historyTargetFor,
  maintenancePlantScope,
  isSaveInFlight,
  leadsAnyActivity,
  NO_ACTIVITIES_HINT,
  NO_ACTIVITIES_TITLE,
  NO_HISTORY_HINT,
  NO_HISTORY_TITLE,
  NO_MASTER_ACTIVITIES_HINT,
  NO_STATUS_HINT,
  NO_STATUS_TITLE,
  READ_ONLY_HINT,
  READ_ONLY_TITLE,
  activityMasterOptions,
  canRecordProductionStatus,
  canTypeNewActivity,
  isTypedActivity,
  parseActivitySelection,
  typedActivityValue,
  withTypedActivityOption,
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
  assert.equal(activityLabel({ activity_code: "FMTL" }), "FMTL");
  assert.equal(activityLabel({}), VALUE_UNAVAILABLE);
  // A typed activity arrives with its name already resolved server-side, so
  // the very same function renders it.
  assert.equal(activityLabel({ activity_name: "HIERARCHY QA/QC" }), "HIERARCHY QA/QC");
});

// Activity Master, the Head's source. Deliberately unrelated to STAFFING: the
// point of the change is that a Head is no longer limited to staffed work.
const ACTIVITY_MASTER = [
  { id: "am-mtl", name: "MTL PREPARATION", level: "activity", is_active: true },
  { id: "am-tag", name: "TAG ESTIMATION", level: "activity", is_active: true },
  { id: "am-idb", name: "1ST STAGE IDB", level: "activity", is_active: true },
  // Not offered: retired master data, and a sub-activity the backend refuses.
  { id: "am-old", name: "RETIRED", level: "activity", is_active: false },
  { id: "am-sub", name: "FMTL REWORK", level: "sub_activity", is_active: true },
];

test("the Head's list is Activity Master, not the project's staffing", () => {
  // The whole point of the change: a project with no staffing at all still has
  // production to report, so the Head sees every Activity Master activity.
  const options = submittableActivityOptions(STAFFING, ACTIVITY_MASTER, {
    canManage: false,
    isHead: true,
    employeeId: "emp-head",
  });
  // Activity Master ids, not the staffing's act-* ones.
  assert.deepEqual(options.map((o) => o.id), ["am-idb", "am-mtl", "am-tag"]);
  // Sorted by the label actually shown.
  assert.deepEqual(
    options.map((o) => o.label),
    ["1ST STAGE IDB", "MTL PREPARATION", "TAG ESTIMATION"],
  );
});

test("a Head with no staffing on the project still has every activity", () => {
  const options = submittableActivityOptions([], ACTIVITY_MASTER, {
    canManage: false,
    isHead: true,
    employeeId: "emp-head",
  });
  assert.equal(options.length, 3);
});

test("retired activities and sub-activities are never offered", () => {
  const ids = activityMasterOptions(ACTIVITY_MASTER).map((o) => o.id);
  assert.equal(ids.includes("am-old"), false);
  assert.equal(ids.includes("am-sub"), false);
});

test("an Activity Lead may submit only for the activity they lead", () => {
  // Unchanged: a Lead's authority is over the activity they were given, and it
  // still comes from the project's staffing - not from Activity Master.
  const options = submittableActivityOptions(STAFFING, ACTIVITY_MASTER, {
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
      submittableActivityOptions(STAFFING, ACTIVITY_MASTER, {
        canManage: false,
        isHead: false,
        employeeId,
      }),
      [],
    );
  }
});

// --- who may write at all ---------------------------------------------------

test("the PM is READ-ONLY on this tab", () => {
  // Deliberate, and the one rule this change is most about. The PM reads every
  // project's status and downloads the cumulative report; the updates are made
  // by the people who did the work.
  const pm = { canManage: true, isHead: false, employeeId: "emp-pm" };
  assert.equal(canRecordProductionStatus(STAFFING, pm), false);
  assert.equal(canTypeNewActivity(pm), false);
  assert.deepEqual(submittableActivityOptions(STAFFING, ACTIVITY_MASTER, pm), []);
});

test("the Head writes, and is the only one who may type an activity", () => {
  const head = { canManage: false, isHead: true, employeeId: "emp-head" };
  const lead = { canManage: false, isHead: false, employeeId: LEAD_EMP };
  assert.equal(canRecordProductionStatus(STAFFING, head), true);
  assert.equal(canRecordProductionStatus(STAFFING, lead), true);
  assert.equal(canTypeNewActivity(head), true);
  // A Lead's authority is over one named Activity Master activity - there is
  // nothing for a typed name to attach to.
  assert.equal(canTypeNewActivity(lead), false);
});

test("someone who neither heads nor leads cannot record", () => {
  assert.equal(
    canRecordProductionStatus(STAFFING, {
      canManage: false,
      isHead: false,
      employeeId: "emp-nobody",
    }),
    false,
  );
});

// --- a typed activity -------------------------------------------------------

test("a typed activity is carried as a prefixed selection, then split", () => {
  const value = typedActivityValue("  HIERARCHY QA/QC  ");
  assert.equal(value, "new:HIERARCHY QA/QC");
  assert.equal(isTypedActivity(value), true);
  assert.deepEqual(parseActivitySelection(value), {
    activity_id: null,
    activity_label: "HIERARCHY QA/QC",
  });
});

test("a chosen activity is sent as an id, never as a label", () => {
  const id = "3f1b2c44-0000-4000-8000-000000000001";
  assert.equal(isTypedActivity(id), false);
  assert.deepEqual(parseActivitySelection(id), {
    activity_id: id,
    activity_label: null,
  });
});

test("exactly one of id / label is ever produced", () => {
  for (const value of ["new:MTL", "act-1", "", null, undefined, "new:   "]) {
    const { activity_id, activity_label } = parseActivitySelection(value);
    assert.equal(
      Number(activity_id !== null) + Number(activity_label !== null) <= 1,
      true,
      `both set for ${String(value)}`,
    );
  }
});

test("a typed activity is shown in the dropdown while it is the selection", () => {
  const options = activityMasterOptions(ACTIVITY_MASTER);
  const withTyped = withTypedActivityOption(options, "new:HIERARCHY QA/QC");
  assert.equal(withTyped.length, options.length + 1);
  assert.deepEqual(withTyped[withTyped.length - 1], {
    id: "new:HIERARCHY QA/QC",
    label: "HIERARCHY QA/QC",
  });
  // A chosen activity is already in the list - nothing is appended.
  assert.deepEqual(withTypedActivityOption(options, "am-mtl"), options);
  assert.deepEqual(withTypedActivityOption(options, ""), options);
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

test("the read-only Project line is the project's code", () => {
  assert.equal(
    formatProjectDisplay({ code: "4716-LC25102900", name: "Execution of..." }),
    "4716-LC25102900",
  );
  // The descriptive name is the fallback only when there is no code.
  assert.equal(formatProjectDisplay({ name: "Unnamed" }), "Unnamed");
  assert.equal(formatProjectDisplay(null), VALUE_UNAVAILABLE);
});

test("the plant dropdown is scoped by the project's Planning Plant code", () => {
  // This is what gets handed to `useMaintenancePlantOptions(true, code, !!code)`
  // - the SAME hook and the SAME scoping the Project Edit page uses, so the
  // two dropdowns can never offer different plants for one project.
  assert.equal(
    maintenancePlantScope({ code: "4460-GC22104900", planning_plant_code: "2300" }),
    "2300",
  );
});

test("a project with no Planning Plant offers no plants, and that is fine", () => {
  // undefined disables the dropdown rather than falling back to "all plants" -
  // and the update still saves with no plant at all.
  assert.equal(maintenancePlantScope({ code: "TESTING001" }), undefined);
  assert.equal(maintenancePlantScope({ code: "X", planning_plant_code: "" }), undefined);
  assert.equal(maintenancePlantScope({ code: "X", planning_plant_code: "  " }), undefined);
  assert.equal(maintenancePlantScope(null), undefined);
});

test("no plant is ever spliced into the Project line", () => {
  // The plant shown on this form is the Maintenance Plant the user SELECTS,
  // which is its own field. The Planning Plant in particular must never be
  // rendered as this record's plant.
  assert.equal(
    formatProjectDisplay({ code: "4716-LC25102900", planning_plant_code: "2400" }),
    "4716-LC25102900",
  );
  assert.equal(
    formatProjectDisplay({ code: "4716-LC25102900", planning_plant_code: "2400" }).includes(
      "2400",
    ),
    false,
  );
});

// ---------------------------------------------------------------------------
// 7. The form body — what is submitted, and what is not
// ---------------------------------------------------------------------------

function values(over: Partial<ProductionStatusFormValues> = {}): ProductionStatusFormValues {
  return { ...EMPTY_PRODUCTION_STATUS_FORM, ...over };
}

test("the body carries only the ten fields the user entered", () => {
  const body = toProductionStatusBody(
    values({
      revision: "REV-0",
      activity_id: "act-tag",
      maintenance_plant_id: "plant-kahm",
      status: "closed",
      tag_count: "225",
      completed_on: "2025-12-05",
      remarks: "Closed after QC",
    }),
  );
  assert.deepEqual(Object.keys(body).sort(), [
    "activity_id",
    "activity_label",
    "completed_on",
    "crs_count",
    "doc_count",
    "maintenance_plant_id",
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

test("the selected maintenance plant is submitted as its identifier", () => {
  const body = toProductionStatusBody(
    values({ revision: "REV-0", activity_id: "a", maintenance_plant_id: "plant-kahm" }),
  );
  // The plant's id, not its code and not its label.
  assert.equal(body.maintenance_plant_id, "plant-kahm");
});

test("no maintenance plant is sent as null, never \"\" and never guessed", () => {
  const body = toProductionStatusBody(values({ revision: "REV-0", activity_id: "a" }));
  assert.equal(body.maintenance_plant_id, null);
  // Selecting nothing must not be rejected by the form - a project whose
  // Planning Plant has no Maintenance Plants has none to offer.
  assert.equal(
    productionStatusFormSchema.safeParse(
      values({ revision: "REV-0", activity_id: "a", maintenance_plant_id: "" }),
    ).success,
    true,
  );
});

test("a saved plant is kept for the next update in the same sitting", () => {
  const next = resetAfterSave(
    values({
      revision: "REV-0",
      activity_id: "a",
      maintenance_plant_id: "plant-kahm",
      tag_count: "225",
    }),
  );
  assert.equal(next.maintenance_plant_id, "plant-kahm");
  // ...while what was asserted about THAT update is cleared.
  assert.equal(next.tag_count, "");
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

// ===========================================================================
// Phase 3 — workflow hardening
// ===========================================================================

// ---------------------------------------------------------------------------
// 11. Revision isolation — REV-0 and REV-1 are separate trails
// ---------------------------------------------------------------------------

const PROJECT = "proj-1";

test("a row's History opens that row's own revision AND activity", () => {
  const rows = buildProductionStatusRows(
    [
      record({ id: "a", revision: "REV-0", activity_id: "act-mtl", activity_name: "MTL PREPARATION" }),
      record({ id: "b", revision: "REV-1", activity_id: "act-mtl", activity_name: "MTL PREPARATION" }),
    ],
    fmt,
  );
  assert.deepEqual(historyTargetFor(rows[0]), {
    activityId: "act-mtl",
    typedActivity: null,
    activityLabel: "MTL PREPARATION",
    revision: "REV-0",
  });
  assert.deepEqual(historyTargetFor(rows[1]), {
    activityId: "act-mtl",
    typedActivity: null,
    activityLabel: "MTL PREPARATION",
    revision: "REV-1",
  });
});

test("a typed activity's row opens its own trail, by name", () => {
  // It has no id to filter on, so the name is what identifies its history -
  // exactly the way the record itself names its activity.
  const [row] = buildProductionStatusRows(
    [
      record({
        id: "t",
        activity_id: null,
        activity_label: "HIERARCHY QA/QC",
        activity_name: "HIERARCHY QA/QC",
        activity_code: null,
      }),
    ],
    fmt,
  );
  assert.equal(row.activity, "HIERARCHY QA/QC");
  assert.deepEqual(historyTargetFor(row), {
    activityId: null,
    typedActivity: "HIERARCHY QA/QC",
    activityLabel: "HIERARCHY QA/QC",
    revision: "REV-0",
  });
});

test("REV-0 and REV-1 of one activity are two different cached datasets", () => {
  // The filter is part of the query key, so opening REV-0's history can never
  // render REV-1's rows out of the cache - and the request itself carries both
  // filters, which the backend ANDs.
  const rev0 = productionStatusKeys.history(PROJECT, {
    activityId: "act-mtl",
    revision: "REV-0",
  });
  const rev1 = productionStatusKeys.history(PROJECT, {
    activityId: "act-mtl",
    revision: "REV-1",
  });
  assert.notDeepEqual(rev0, rev1);
  // The empty slot is the typed-activity name, which an Activity Master row
  // does not have - see keys.ts.
  assert.deepEqual([...rev0],
    ["production-status", "history", PROJECT, "act-mtl", "", "REV-0"]);
  assert.deepEqual([...rev1],
    ["production-status", "history", PROJECT, "act-mtl", "", "REV-1"]);
});

test("a typed activity's trail is its own cached dataset", () => {
  // A typed activity has no id, so without the label in the key every typed
  // activity on a project would share one cache entry.
  const hierarchy = productionStatusKeys.history(PROJECT, {
    activityLabel: "HIERARCHY QA/QC",
    revision: "REV-0",
  });
  const bom = productionStatusKeys.history(PROJECT, {
    activityLabel: "BOM QA/QC",
    revision: "REV-0",
  });
  assert.notDeepEqual(hierarchy, bom);
  assert.deepEqual([...hierarchy],
    ["production-status", "history", PROJECT, "", "HIERARCHY QA/QC", "REV-0"]);
});

test("the same revision of two activities is two different cached datasets", () => {
  const mtl = productionStatusKeys.history(PROJECT, {
    activityId: "act-mtl",
    revision: "REV-0",
  });
  const fmtl = productionStatusKeys.history(PROJECT, {
    activityId: "act-fmtl",
    revision: "REV-0",
  });
  const bom = productionStatusKeys.history(PROJECT, {
    activityId: "act-bom",
    revision: "REV-0",
  });
  assert.equal(new Set([mtl, fmtl, bom].map((k) => k.join("|"))).size, 3);
});

test("an unfiltered history is not the same dataset as a filtered one", () => {
  assert.notDeepEqual(
    productionStatusKeys.history(PROJECT, {}),
    productionStatusKeys.history(PROJECT, { activityId: "act-mtl", revision: "REV-0" }),
  );
  // Two projects never share a trail either.
  assert.notDeepEqual(
    productionStatusKeys.history("proj-1", { revision: "REV-0" }),
    productionStatusKeys.history("proj-2", { revision: "REV-0" }),
  );
  assert.notDeepEqual(
    productionStatusKeys.latest("proj-1"),
    productionStatusKeys.latest("proj-2"),
  );
});

test("current status keeps one row per revision + activity, side by side", () => {
  // The backend derives these; the UI must render both, not merge them.
  const rows = buildProductionStatusRows(
    [
      record({ id: "a", revision: "REV-0", activity_id: "act-mtl", activity_name: "MTL PREPARATION",
               status: "closed", tag_count: 500 }),
      record({ id: "b", revision: "REV-1", activity_id: "act-mtl", activity_name: "MTL PREPARATION",
               status: "in_progress", tag_count: 300 }),
    ],
    fmt,
  );
  assert.equal(rows.length, 2);
  assert.deepEqual(rows.map((r) => `${r.revision} ${r.status} ${r.tag}`), [
    "REV-0 CLOSED 500",
    "REV-1 IN PROGRESS 300",
  ]);
});

// ---------------------------------------------------------------------------
// 12. Activity isolation — updating one activity leaves the others alone
// ---------------------------------------------------------------------------

test("activities on the same revision render independently", () => {
  const rows = buildProductionStatusRows(
    [
      record({ id: "m", activity_id: "act-mtl", activity_name: "MTL PREPARATION", tag_count: 500 }),
      record({ id: "f", activity_id: "act-fmtl", activity_name: "FMTL PREPARATION", tag_count: 120 }),
      record({ id: "b", activity_id: "act-bom", activity_name: "BOM PREPARATION", tag_count: 40 }),
    ],
    fmt,
  );
  assert.deepEqual(rows.map((r) => r.activity), [
    "MTL PREPARATION",
    "FMTL PREPARATION",
    "BOM PREPARATION",
  ]);
  assert.deepEqual(rows.map((r) => r.tag), ["500", "120", "40"]);
  // Every row opens its own trail.
  assert.deepEqual(
    rows.map((r) => historyTargetFor(r).activityId),
    ["act-mtl", "act-fmtl", "act-bom"],
  );
});

// ---------------------------------------------------------------------------
// 13. Multiple users — each update keeps its own author
// ---------------------------------------------------------------------------

test("each row shows the person who recorded it, not one shared author", () => {
  const rows = buildProductionStatusRows(
    [
      record({ id: "m", activity_name: "MTL PREPARATION", created_by_name: "Santhosh Kumar" }),
      record({ id: "f", activity_name: "FMTL PREPARATION", created_by_name: "Alex Manager" }),
    ],
    fmt,
  );
  assert.deepEqual(rows.map((r) => r.by), ["Santhosh Kumar", "Alex Manager"]);
});

test("a history trail keeps the author of every individual update", () => {
  const rows = buildProductionStatusRows(
    [
      record({ id: "3", tag_count: 225, created_by_name: "Alex Manager" }),
      record({ id: "2", tag_count: 180, created_by_name: "Santhosh Kumar" }),
      record({ id: "1", tag_count: 100, created_by_name: "Santhosh Kumar" }),
    ],
    fmt,
  );
  assert.deepEqual(rows.map((r) => r.by), [
    "Alex Manager",
    "Santhosh Kumar",
    "Santhosh Kumar",
  ]);
  // No role word ever substitutes for a person.
  for (const r of rows) {
    for (const role of ["Activity Lead", "Project Head", "PM", "Head"]) {
      assert.notEqual(r.by, role);
    }
  }
});

// ---------------------------------------------------------------------------
// 14. Count independence across successive updates
// ---------------------------------------------------------------------------

test("a later update changing one unit leaves the other three as submitted", () => {
  const first = { tag_count: 225, doc_count: 100, spares_count: 50, crs_count: 20 };
  const second = { ...first, tag_count: 300 };
  const rows = buildProductionStatusRows(
    [record({ id: "2", ...second }), record({ id: "1", ...first })],
    fmt,
  );
  assert.deepEqual(
    [rows[0].tag, rows[0].doc, rows[0].spares, rows[0].crs],
    ["300", "100", "50", "20"],
  );
  assert.deepEqual(
    [rows[1].tag, rows[1].doc, rows[1].spares, rows[1].crs],
    ["225", "100", "50", "20"],
  );
});

test("the form submits the four counts exactly as typed, deriving none of them", () => {
  const body = toProductionStatusBody(
    values({
      revision: "REV-0",
      activity_id: "act-mtl",
      tag_count: "225",
      doc_count: "100",
      spares_count: "50",
      crs_count: "20",
    }),
  );
  assert.deepEqual(
    [body.tag_count, body.doc_count, body.spares_count, body.crs_count],
    [225, 100, 50, 20],
  );
  // No total, and no unit computed from another.
  assert.equal("total_count" in body, false);
  assert.equal(Object.keys(body).filter((k) => k.endsWith("_count")).length, 4);
});

// ---------------------------------------------------------------------------
// 15. Status behaviour — two values, and a change is a NEW record
// ---------------------------------------------------------------------------

test("IN PROGRESS submits with no completion date invented for it", () => {
  const body = toProductionStatusBody(
    values({ revision: "REV-0", activity_id: "act-mtl", status: "in_progress" }),
  );
  assert.equal(body.status, "in_progress");
  assert.equal(body.completed_on, null);
});

test("a status change is submitted as a whole new record, not a patch", () => {
  // resetAfterSave carries the identity forward and clears the assertions, so
  // the follow-up save is a complete record - nothing is 'left over' from the
  // previous one to imply an edit.
  const closed = resetAfterSave(
    values({ revision: "REV-0", activity_id: "act-mtl", status: "in_progress", tag_count: "180" }),
  );
  const body = toProductionStatusBody({ ...closed, status: "closed", tag_count: "225",
                                        completed_on: "2025-12-05" });
  assert.deepEqual(body, {
    revision: "REV-0",
    activity_id: "act-mtl",
    // An id was chosen, so the typed-name field is null - exactly one of the
    // two is ever set.
    activity_label: null,
    // No plant was chosen on either save - null, never inferred.
    maintenance_plant_id: null,
    status: "closed",
    tag_count: 225,
    doc_count: 0,
    spares_count: 0,
    crs_count: 0,
    completed_on: "2025-12-05",
    remarks: null,
  });
  // No id and no edit marker: the API has no PATCH to send them to.
  assert.equal("id" in body, false);
});

// ---------------------------------------------------------------------------
// 16. Completed On — a calendar date, never shifted
// ---------------------------------------------------------------------------

test("a completion date never slips a day, whatever the viewer's timezone", () => {
  // The formatter reads the digits, so the result does not depend on the
  // runner's TZ at all - asserted here by running under an extreme one.
  const before = process.env.TZ;
  try {
    for (const tz of ["Pacific/Kiritimati", "Pacific/Midway", "UTC", "Asia/Kolkata"]) {
      process.env.TZ = tz;
      assert.equal(formatProductionDate("2025-12-05"), "05 Dec 2025", tz);
      assert.equal(formatProductionDate("2026-01-01"), "01 Jan 2026", tz);
      assert.equal(formatProductionDate("2025-12-31"), "31 Dec 2025", tz);
    }
  } finally {
    if (before === undefined) delete process.env.TZ;
    else process.env.TZ = before;
  }
});

test("the date the user picked is the date that is sent", () => {
  const body = toProductionStatusBody(
    values({ revision: "REV-0", activity_id: "a", completed_on: "2025-12-05" }),
  );
  // A plain YYYY-MM-DD string, never a Date turned into an instant.
  assert.equal(body.completed_on, "2025-12-05");
});

// ---------------------------------------------------------------------------
// 17. Remarks — multiline, preserved whole
// ---------------------------------------------------------------------------

test("a multiline remark survives to the API and back unchanged", () => {
  const remark = "FMTL submitted to QE.\nAwaiting response.\nPunch list received.";
  const body = toProductionStatusBody(
    values({ revision: "REV-0", activity_id: "a", remarks: remark }),
  );
  assert.equal(body.remarks, remark);
  assert.equal(body.remarks?.split("\n").length, 3);

  const rows = buildProductionStatusRows([record({ remarks: remark })], fmt);
  assert.equal(rows[0].remarks, remark);
  // Nothing is truncated or collapsed - the cell renders it with
  // `whitespace-pre-wrap`, so every line is visible.
  assert.equal(rows[0].remarks?.includes("\n"), true);
  assert.equal(rows[0].remarks?.endsWith("Punch list received."), true);
});

// ---------------------------------------------------------------------------
// 18. Double submission
// ---------------------------------------------------------------------------

test("Save is blocked from the click until the response lands", () => {
  // Before the click.
  assert.equal(isSaveInFlight({ isPending: false, isSubmitting: false }), false);
  // Clicked: react-hook-form flips isSubmitting before the async validation, so
  // the button is already disabled while no request exists yet.
  assert.equal(isSaveInFlight({ isPending: false, isSubmitting: true }), true);
  // Request in flight.
  assert.equal(isSaveInFlight({ isPending: true, isSubmitting: true }), true);
  assert.equal(isSaveInFlight({ isPending: true, isSubmitting: false }), true);
  // Settled - the next, intentional update may be saved.
  assert.equal(isSaveInFlight({ isPending: false, isSubmitting: false }), false);
});

test("two intentional identical updates are both valid submissions", () => {
  // The guard suppresses a repeated click, never a repeated update: recording
  // the same figures twice is legitimate append-only history and the client
  // must not reject or de-duplicate it.
  const v = values({ revision: "REV-0", activity_id: "act-mtl", tag_count: "225" });
  assert.equal(productionStatusFormSchema.safeParse(v).success, true);
  assert.deepEqual(toProductionStatusBody(v), toProductionStatusBody(v));
  // ...and the form is left ready to make exactly that second update.
  const next = resetAfterSave(v);
  assert.equal(next.revision, "REV-0");
  assert.equal(next.activity_id, "act-mtl");
  assert.equal(productionStatusFormSchema.safeParse(next).success, true);
});

// ---------------------------------------------------------------------------
// 19. Empty states — every one of them says something
// ---------------------------------------------------------------------------

test("each empty case has its own copy, so no panel can render blank", () => {
  const copy = [
    NO_STATUS_TITLE, NO_STATUS_HINT,
    NO_HISTORY_TITLE, NO_HISTORY_HINT,
    NO_ACTIVITIES_TITLE, NO_ACTIVITIES_HINT,
    NO_MASTER_ACTIVITIES_HINT,
    READ_ONLY_TITLE, READ_ONLY_HINT,
  ];
  for (const text of copy) assert.equal(text.trim().length > 0, true);
  // "you lead nothing here", "the master list is empty" and "you may only read
  // this" are three different situations and must not share a sentence.
  assert.notEqual(NO_ACTIVITIES_HINT, NO_MASTER_ACTIVITIES_HINT);
  assert.notEqual(NO_ACTIVITIES_HINT, READ_ONLY_HINT);
  assert.notEqual(NO_STATUS_TITLE, NO_HISTORY_TITLE);
});

test("no data means an empty list, never a thrown render", () => {
  for (const input of [null, undefined, []] as const) {
    assert.deepEqual(buildProductionStatusRows(input, fmt), []);
  }
});


// --- deleting a record you recorded (UX Phase 1) ----------------------------

test("only the author of a row may delete it", () => {
  const mine = { createdBy: "user-1" };
  const theirs = { createdBy: "user-2" };

  assert.equal(canDeleteProductionStatusRow(mine, "user-1"), true);
  assert.equal(canDeleteProductionStatusRow(theirs, "user-1"), false);

  // Never a role and never a name: an unknown author on either side is "no",
  // so a row can't become deletable by an id going missing.
  assert.equal(canDeleteProductionStatusRow({ createdBy: null }, "user-1"), false);
  assert.equal(canDeleteProductionStatusRow(mine, null), false);
  assert.equal(canDeleteProductionStatusRow(mine, undefined), false);
  assert.equal(canDeleteProductionStatusRow({ createdBy: null }, null), false);
});

test("a row carries the author's id alongside the displayed name", () => {
  const [row] = buildProductionStatusRows(
    [
      {
        id: "r1",
        revision: "REV-0",
        activity_id: "a1",
        activity_name: "FMTL",
        status: "in_progress",
        tag_count: 180,
        doc_count: 0,
        spares_count: 0,
        crs_count: 0,
        created_by: "user-1",
        created_by_name: "Santhosh Kumar",
        created_at: "2026-08-31T10:00:00Z",
      },
    ],
    () => "31 Aug 2026",
  );

  assert.equal(row.createdBy, "user-1");
  assert.equal(row.by, "Santhosh Kumar");
  // The display name is not the ownership key - two people can share one.
  assert.equal(canDeleteProductionStatusRow(row, "user-1"), true);
  assert.equal(canDeleteProductionStatusRow(row, "Santhosh Kumar"), false);
});
