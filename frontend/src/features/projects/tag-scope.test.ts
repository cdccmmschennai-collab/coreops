/**
 * Project Tag Scope — the managed set / revise workflow (Phase 4).
 *
 * The repo's frontend harness is `node --test` over `src/**​/*.test.ts` (see
 * package.json `test:unit`): plain TypeScript, no jsdom / React Testing
 * Library. So the rules are pinned where they actually live — the pure modules
 * the components delegate to:
 *
 *   scope.ts    count parsing, the no-op rule, error wording, history rows
 *   schemas.ts  the form schema and the PUT body it produces
 *   permissions.ts  who may open the tab and press the buttons
 *
 * `tag-scope-tab.tsx` and `tag-scope-dialog.tsx` render exactly what these
 * return and decide nothing on their own, which is what makes that split worth
 * having. Rendering itself is covered by the browser pass.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildTagScopeHistoryRows,
  buildTagScopeView,
  isNoOpScopeChange,
  NO_PREVIOUS_VALUE,
  parseTagCount,
  REASON_REQUIRED_ERROR,
  TAG_COUNT_ERROR,
  TAG_SCOPE_CONFLICT_MESSAGE,
  tagScopeActionLabel,
  tagScopeErrorMessage,
  type TagScopeRevisionInput,
} from "./scope.ts";
import { tagScopeFormSchema, toTagScopeBody, type TagScopeFormValues } from "./schemas.ts";
import {
  canEditProject,
  canManageTagScope,
  canViewTagScope,
  type ProjectViewer,
} from "./permissions.ts";

// ---------- estimated count validation (spec §5) ----------
test("a count must be a whole number greater than 0", () => {
  for (const good of ["1", "1000", "2500", " 2500 "]) {
    assert.notEqual(parseTagCount(good), null, good);
  }
  assert.equal(parseTagCount("1"), 1);
  assert.equal(parseTagCount("2500"), 2500);
});

test("blank, zero, negative, fractional and non-numeric counts are refused", () => {
  for (const bad of ["", "   ", "0", "-1", "2.5", "abc", "1,000", "1e3", "+1", "1.0", null, undefined]) {
    assert.equal(parseTagCount(bad), null, JSON.stringify(bad));
  }
});

test("zero is refused specifically — unknown scope is null, never 0", () => {
  assert.equal(parseTagCount("0"), null);
  assert.equal(parseTagCount("00"), null);
});

// ---------- the form schema (spec §4, §11) ----------
function values(over: Partial<TagScopeFormValues> = {}): TagScopeFormValues {
  return { estimated_tag_count: "1000", status: "PROVISIONAL", reason: "", ...over };
}

test("the initial estimate may be saved without a reason", () => {
  const parsed = tagScopeFormSchema(false).safeParse(values());
  assert.equal(parsed.success, true);
});

test("revising an established scope requires a reason", () => {
  const parsed = tagScopeFormSchema(true).safeParse(values({ estimated_tag_count: "2500" }));
  assert.equal(parsed.success, false);
  assert.equal(parsed.error?.issues[0]?.message, REASON_REQUIRED_ERROR);
});

test("whitespace is not a reason", () => {
  const parsed = tagScopeFormSchema(true).safeParse(values({ reason: "    " }));
  assert.equal(parsed.success, false);
});

test("a real reason passes the revision schema", () => {
  const parsed = tagScopeFormSchema(true).safeParse(
    values({ reason: "Additional tags identified from new reference documents" }),
  );
  assert.equal(parsed.success, true);
});

test("the form rejects a bad count with the same rule the Save button reads", () => {
  for (const bad of ["", "0", "-1", "2.5", "abc"]) {
    const parsed = tagScopeFormSchema(false).safeParse(values({ estimated_tag_count: bad }));
    assert.equal(parsed.success, false, bad);
    assert.equal(parsed.error?.issues[0]?.message, TAG_COUNT_ERROR);
  }
});

test("the status field accepts only the two supported values — no FINALIZED", () => {
  assert.equal(tagScopeFormSchema(false).safeParse(values({ status: "PROVISIONAL" })).success, true);
  assert.equal(tagScopeFormSchema(false).safeParse(values({ status: "BASELINED" })).success, true);
  const bad = { ...values(), status: "FINALIZED" };
  assert.equal(tagScopeFormSchema(false).safeParse(bad).success, false);
});

// ---------- the PUT body (spec §7, §12, §21) ----------
test("the body carries the count, status, reason and the revision it was opened against", () => {
  const body = toTagScopeBody(
    values({ estimated_tag_count: "2500", status: "BASELINED", reason: "FMTL scope established" }),
    2,
  );
  assert.deepEqual(body, {
    estimated_tag_count: 2500,
    status: "BASELINED",
    reason: "FMTL scope established",
    expected_revision: 2,
  });
});

test("the frontend never sends a revision number, an author or a timestamp", () => {
  const body = toTagScopeBody(values(), 0) as Record<string, unknown>;
  for (const owned of ["revision", "changed_by", "updated_at", "tag_scope_revision"]) {
    assert.equal(owned in body, false, owned);
  }
  // expected_revision is the baseline being checked against, not the new number.
  assert.equal(body.expected_revision, 0);
});

test("an omitted reason is sent as null so the server can apply its own default", () => {
  assert.equal(toTagScopeBody(values({ reason: "   " }), 0).reason, null);
});

test("a reason is trimmed before it is sent", () => {
  assert.equal(toTagScopeBody(values({ reason: "  Vendor issued revised tag register.  " }), 1).reason, "Vendor issued revised tag register.");
});

test("the count reaches the body as a number, not the typed string", () => {
  assert.equal(toTagScopeBody(values({ estimated_tag_count: " 2500 " }), 1).estimated_tag_count, 2500);
});

// ---------- the no-change rule (spec §13) ----------
const CURRENT = { estimatedTagCount: 2500, status: "BASELINED" as const };

test("resubmitting the stored scope verbatim is a no-op", () => {
  assert.equal(isNoOpScopeChange(CURRENT, { estimatedTagCount: 2500, status: "BASELINED" }), true);
});

test("a changed count or a changed status is a real revision", () => {
  assert.equal(isNoOpScopeChange(CURRENT, { estimatedTagCount: 2700, status: "BASELINED" }), false);
  assert.equal(isNoOpScopeChange(CURRENT, { estimatedTagCount: 2500, status: "PROVISIONAL" }), false);
});

test("an unparseable count is never mistaken for the stored value", () => {
  // The button must stay disabled for "abc" because it is invalid, not because
  // it matches — these are different reasons and must not be conflated.
  assert.equal(isNoOpScopeChange(CURRENT, { estimatedTagCount: null, status: "BASELINED" }), false);
});

// ---------- lifecycle (spec §6, §14, §15, §16) ----------
test("1000 provisional -> 2000 baselined -> 2500 baselined are all real changes", () => {
  const r1 = { estimatedTagCount: 1000, status: "PROVISIONAL" as const };
  const r2 = { estimatedTagCount: 2000, status: "BASELINED" as const };
  const r3 = { estimatedTagCount: 2500, status: "BASELINED" as const };
  assert.equal(isNoOpScopeChange(r1, r2), false);
  assert.equal(isNoOpScopeChange(r2, r3), false);
});

test("a reduction is a permitted change in this phase", () => {
  assert.equal(
    isNoOpScopeChange({ estimatedTagCount: 2500, status: "BASELINED" }, { estimatedTagCount: 2200, status: "BASELINED" }),
    false,
  );
  assert.equal(tagScopeFormSchema(true).safeParse(values({ estimated_tag_count: "2200", status: "BASELINED", reason: "Scope consolidation" })).success, true);
});

// ---------- the action button (spec §3, §10) ----------
test("the first estimate is Set, a later one is Revise", () => {
  assert.equal(tagScopeActionLabel("unconfigured"), "Set Tag Scope");
  assert.equal(tagScopeActionLabel("configured"), "Revise Tag Scope");
});

// ---------- the configured panel (spec §9) ----------
test("a configured project shows its audit stamp alongside the values", () => {
  const v = buildTagScopeView({
    scopeType: "TAG_BASED",
    estimatedTagCount: 2500,
    tagScopeStatus: "BASELINED",
    tagScopeRevision: 3,
    updatedAt: "Aug 7, 2026, 05:15 PM",
    updatedByName: "Project Head",
  });
  assert.equal(v.kind, "configured");
  assert.deepEqual(
    v.rows.map((r) => [r.label, r.value]),
    [
      ["Estimated Tags", "2,500"],
      ["Status", "Confirmed Scope"],
      ["Revision", "3"],
      ["Last Updated", "Aug 7, 2026, 05:15 PM"],
      ["Updated By", "Project Head"],
    ],
  );
});

test("an unconfigured project shows no audit rows — there is nothing to attribute", () => {
  const v = buildTagScopeView({
    scopeType: "TAG_BASED",
    estimatedTagCount: null,
    tagScopeStatus: null,
    tagScopeRevision: 0,
    updatedAt: null,
    updatedByName: null,
  });
  assert.equal(v.kind, "unconfigured");
  assert.deepEqual(v.rows.map((r) => r.label), ["Estimated Tags", "Status", "Revision"]);
});

test("a NONE project still offers no scope values in this phase", () => {
  const v = buildTagScopeView({
    scopeType: "NONE",
    estimatedTagCount: null,
    tagScopeStatus: null,
    tagScopeRevision: 0,
  });
  assert.equal(v.kind, "not-tag-based");
  assert.deepEqual(v.rows, []);
  assert.match(v.hint, /Edit Project page/);
});

// ---------- the history table (spec §17) ----------
const HISTORY: TagScopeRevisionInput[] = [
  {
    id: "r1",
    revision: 1,
    previous_estimated_tag_count: null,
    new_estimated_tag_count: 1000,
    previous_status: null,
    new_status: "PROVISIONAL",
    reason: "Initial project estimate",
    changed_by_name: "PM",
    created_at: "2026-07-15T10:00:00Z",
  },
  {
    id: "r2",
    revision: 2,
    previous_estimated_tag_count: 1000,
    new_estimated_tag_count: 2000,
    previous_status: "PROVISIONAL",
    new_status: "BASELINED",
    reason: "FMTL scope established",
    changed_by_name: "Head",
    created_at: "2026-07-31T10:00:00Z",
  },
  {
    id: "r3",
    revision: 3,
    previous_estimated_tag_count: 2000,
    new_estimated_tag_count: 2500,
    previous_status: "BASELINED",
    new_status: "BASELINED",
    reason: "Additional tags identified from new reference documents",
    changed_by_name: "Head",
    created_at: "2026-08-07T17:15:00Z",
  },
];

const isoDate = (iso: string) => iso.slice(0, 10);

test("history is newest first", () => {
  const rows = buildTagScopeHistoryRows(HISTORY, isoDate);
  assert.deepEqual(rows.map((r) => r.revision), [3, 2, 1]);
});

test("every revision is preserved, none collapsed", () => {
  assert.equal(buildTagScopeHistoryRows(HISTORY, isoDate).length, 3);
});

test("the first revision shows no previous value rather than a fake zero", () => {
  const first = buildTagScopeHistoryRows(HISTORY, isoDate).find((r) => r.revision === 1);
  assert.equal(first?.previous, NO_PREVIOUS_VALUE);
  assert.notEqual(first?.previous, "0");
  assert.equal(first?.next, "1,000");
});

test("a later revision shows the value it superseded", () => {
  const rows = buildTagScopeHistoryRows(HISTORY, isoDate);
  assert.deepEqual(
    rows.map((r) => [r.previous, r.next]),
    [
      ["2,000", "2,500"],
      ["1,000", "2,000"],
      [NO_PREVIOUS_VALUE, "1,000"],
    ],
  );
});

test("history renders the display labels, the reason and the author", () => {
  const [newest] = buildTagScopeHistoryRows(HISTORY, isoDate);
  assert.equal(newest.status, "Confirmed Scope");
  assert.equal(newest.reason, "Additional tags identified from new reference documents");
  assert.equal(newest.updatedBy, "Head");
  assert.equal(newest.date, "2026-08-07");
});

test("a missing author name never renders blank or undefined", () => {
  const rows = buildTagScopeHistoryRows(
    [{ ...HISTORY[0], changed_by_name: "" }],
    isoDate,
  );
  assert.equal(rows[0].updatedBy, "Unknown");
});

test("an empty history is handled without inventing a row", () => {
  assert.deepEqual(buildTagScopeHistoryRows([], isoDate), []);
});

test("building history does not mutate the source order", () => {
  const source = [...HISTORY];
  buildTagScopeHistoryRows(source, isoDate);
  assert.deepEqual(source.map((r) => r.revision), [1, 2, 3]);
});

// ---------- errors and concurrency (spec §19, §20) ----------
test("a stale save gets the documented conflict wording", () => {
  assert.equal(tagScopeErrorMessage(409, "whatever the server said"), TAG_SCOPE_CONFLICT_MESSAGE);
  assert.match(TAG_SCOPE_CONFLICT_MESSAGE, /Refresh and review the latest scope/);
});

test("403 and 404 are explained rather than echoed", () => {
  assert.match(tagScopeErrorMessage(403, null), /permission/i);
  assert.match(tagScopeErrorMessage(404, null), /no longer exists/i);
});

test("a 422 shows the server's human-written reason", () => {
  assert.equal(
    tagScopeErrorMessage(422, "Estimated tag count must be greater than 0."),
    "Estimated tag count must be greater than 0.",
  );
});

test("a 500 or a network failure never leaks internals", () => {
  assert.equal(tagScopeErrorMessage(500, "Traceback (most recent call last): ..."), "Something went wrong. Please try again.");
  assert.match(tagScopeErrorMessage(0, null), /Could not reach the server/);
});

test("no error path can render undefined, null or NaN", () => {
  const cases: [number | null | undefined, string | null | undefined][] = [
    [409, undefined], [403, null], [404, ""], [422, "   "], [500, undefined],
    [0, null], [null, null], [undefined, undefined],
  ];
  for (const [status, message] of cases) {
    const text = tagScopeErrorMessage(status, message);
    assert.equal(typeof text, "string");
    assert.ok(text.length > 0, `${status}`);
    for (const banned of ["undefined", "null", "NaN", "Traceback"]) {
      assert.equal(text.includes(banned), false, `${status}: ${banned}`);
    }
  }
});

// ---------- authorization (spec §8) ----------
const PM: ProjectViewer = { canManage: true, isHead: false };
const ASSIGNED_HEAD: ProjectViewer = { canManage: false, isHead: true };
const OTHER_HEAD: ProjectViewer = { canManage: false, isHead: false };
const MEMBER: ProjectViewer = { canManage: false, isHead: false };

test("a PM may manage tag scope on any project", () => {
  assert.equal(canManageTagScope(PM), true);
  assert.equal(canEditProject(PM), true);
});

test("this project's Head may manage its tag scope", () => {
  assert.equal(canManageTagScope(ASSIGNED_HEAD), true);
});

test("heading another project grants nothing here", () => {
  // isHead is computed against the project on screen, so a Head of project A
  // arrives at project B as an ordinary viewer.
  assert.equal(canManageTagScope(OTHER_HEAD), false);
});

test("an ordinary member or viewer cannot manage tag scope", () => {
  assert.equal(canManageTagScope(MEMBER), false);
});

test("but every one of them can still READ it", () => {
  // The Revise button is what disappears, not the tab.
  assert.equal(canViewTagScope(), true);
});

// ---------- scope guard (spec §24) ----------
test("nothing in this phase exposes progress, remaining or achievement", () => {
  const v = buildTagScopeView({
    scopeType: "TAG_BASED",
    estimatedTagCount: 2500,
    tagScopeStatus: "BASELINED",
    tagScopeRevision: 3,
    updatedAt: "Aug 7, 2026, 05:15 PM",
    updatedByName: "Project Head",
  });
  const labels = v.rows.map((r) => r.label.toLowerCase());
  for (const banned of ["progress", "worked", "remaining", "completion", "achievement", "%"]) {
    assert.equal(labels.some((l) => l.includes(banned)), false, banned);
  }
  const body = toTagScopeBody(values(), 1) as Record<string, unknown>;
  assert.deepEqual(Object.keys(body).sort(), [
    "estimated_tag_count",
    "expected_revision",
    "reason",
    "status",
  ]);
});
