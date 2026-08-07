/**
 * Project scope classification — options, defaults, form round-trip and the
 * Tag Scope placeholder copy.
 *
 * The repo's frontend harness is `node --test` over `src/**​/*.test.ts` (see
 * package.json `test:unit`): plain TypeScript, no jsdom / React Testing
 * Library. So the component-facing behaviour is pinned where it actually lives:
 * `project-edit.tsx` seeds the form through `resolveScopeType`, the form
 * submits through `toCreateBody` / `toUpdateBody`, and `TagScopeTab` renders
 * exactly what `tagScopePlaceholder` returns.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildTagScopeView,
  DEFAULT_PROJECT_SCOPE_TYPE,
  formatTagCount,
  NOT_SET_LABEL,
  PROJECT_SCOPE_TYPES,
  PROJECT_SCOPE_TYPE_LABEL,
  resolveScopeType,
  resolveTagScopeStatus,
  TAG_SCOPE_STATUS_LABEL,
} from "./scope.ts";
import {
  EMPTY_PROJECT_FORM,
  projectFormSchema,
  toCreateBody,
  toUpdateBody,
  type ProjectFormValues,
} from "./schemas.ts";

function form(over: Partial<ProjectFormValues> = {}): ProjectFormValues {
  return { ...EMPTY_PROJECT_FORM, code: "P-1", name: "Apollo", ...over };
}

// ---------- options / labels ----------
test("the selector offers exactly the two classifications, normal first", () => {
  assert.deepEqual([...PROJECT_SCOPE_TYPES], ["NONE", "TAG_BASED"]);
});

test("labels are the approved user-facing wording, never the raw enum", () => {
  assert.equal(PROJECT_SCOPE_TYPE_LABEL.NONE, "Normal / Non-Tag Project");
  assert.equal(PROJECT_SCOPE_TYPE_LABEL.TAG_BASED, "Tag-Based Project");
});

// Test 1 — default
test("a new project form starts as a normal, non-tag project", () => {
  assert.equal(DEFAULT_PROJECT_SCOPE_TYPE, "NONE");
  assert.equal(EMPTY_PROJECT_FORM.scope_type, "NONE");
  assert.equal(toCreateBody(form()).scope_type, "NONE");
});

// Test 2 — create TAG_BASED
test("creating a tag-based project sends TAG_BASED", () => {
  assert.equal(toCreateBody(form({ scope_type: "TAG_BASED" })).scope_type, "TAG_BASED");
});

// Test 7 — edit form displays the stored value
test("the edit form seeds from the stored value in both directions", () => {
  assert.equal(resolveScopeType("TAG_BASED"), "TAG_BASED");
  assert.equal(resolveScopeType("NONE"), "NONE");
});

test("a missing or unknown stored value reads as NONE rather than breaking the page", () => {
  assert.equal(resolveScopeType(null), "NONE");
  assert.equal(resolveScopeType(undefined), "NONE");
  assert.equal(resolveScopeType(""), "NONE");
  assert.equal(resolveScopeType("RANDOM"), "NONE");
  // Stored values are uppercase; a lowercase near-miss is not silently accepted.
  assert.equal(resolveScopeType("tag_based"), "NONE");
});

// Test 8 — saving through Edit
test("changing NONE to TAG_BASED in the edit form reaches the PATCH body", () => {
  assert.equal(toUpdateBody(form({ scope_type: "TAG_BASED" })).scope_type, "TAG_BASED");
});

test("changing TAG_BASED back to NONE also reaches the PATCH body", () => {
  assert.equal(toUpdateBody(form({ scope_type: "NONE" })).scope_type, "NONE");
});

test("an unedited project resubmits its existing classification unchanged", () => {
  // project-edit.tsx seeds defaults from the project; submitting untouched must
  // send the same value back, never silently reclassify.
  const seeded = form({ scope_type: "TAG_BASED" });
  assert.equal(toUpdateBody(seeded).scope_type, "TAG_BASED");
});

// Test 5 (frontend half) — validation
test("the form schema rejects a value outside the two classifications", () => {
  const bad = { ...form(), scope_type: "RANDOM" };
  assert.equal(projectFormSchema.safeParse(bad).success, false);
});

test("the form schema accepts both valid classifications", () => {
  assert.equal(projectFormSchema.safeParse(form({ scope_type: "NONE" })).success, true);
  assert.equal(projectFormSchema.safeParse(form({ scope_type: "TAG_BASED" })).success, true);
});

// ---------- Tag Scope panel (Phase 3, read-only) ----------
const UNSET = { estimatedTagCount: null, tagScopeStatus: null, tagScopeRevision: 0 };

function rowMap(rows: { label: string; value: string }[]): Record<string, string> {
  return Object.fromEntries(rows.map((r) => [r.label, r.value]));
}

// Frontend Test — Tag Scope for a NONE project: visible, non-blank, no values.
test("a non-tag project explains it is not configured and where to change that", () => {
  const v = buildTagScopeView({ scopeType: "NONE", ...UNSET });
  assert.equal(v.kind, "not-tag-based");
  assert.equal(v.message, "This project is not configured as a tag-based project.");
  assert.equal(
    v.hint,
    "Change the Project Scope from the Edit Project page to enable tag-scope functionality.",
  );
  // No scope values are implied for a project that has no scope.
  assert.deepEqual(v.rows, []);
});

test("a NONE project never shows scope values even if stale data is passed", () => {
  const v = buildTagScopeView({
    scopeType: "NONE",
    estimatedTagCount: 2500,
    tagScopeStatus: "BASELINED",
    tagScopeRevision: 3,
  });
  assert.equal(v.kind, "not-tag-based");
  assert.deepEqual(v.rows, []);
});

// Frontend Test — TAG_BASED without an estimate.
test("a tag-based project with no estimate reads Not set / Not set / 0", () => {
  const v = buildTagScopeView({ scopeType: "TAG_BASED", ...UNSET });
  assert.equal(v.kind, "unconfigured");
  assert.equal(v.message, "Scope has not been configured yet.");
  assert.equal(v.hint, "This project is configured as a tag-based project.");
  assert.deepEqual(rowMap(v.rows), {
    "Estimated Tags": "Not set",
    Status: "Not set",
    Revision: "0",
  });
});

test("an unknown scope is never rendered as 0 — unknown and zero differ", () => {
  const v = buildTagScopeView({ scopeType: "TAG_BASED", ...UNSET });
  assert.equal(rowMap(v.rows)["Estimated Tags"], NOT_SET_LABEL);
  assert.notEqual(rowMap(v.rows)["Estimated Tags"], "0");
});

// Frontend Test — configured fixture.
test("a configured tag-based project reads 2,500 / Baselined / 3", () => {
  const v = buildTagScopeView({
    scopeType: "TAG_BASED",
    estimatedTagCount: 2500,
    tagScopeStatus: "BASELINED",
    tagScopeRevision: 3,
  });
  assert.equal(v.kind, "configured");
  assert.deepEqual(rowMap(v.rows), {
    "Estimated Tags": "2,500",
    Status: "Baselined",
    Revision: "3",
  });
});

test("a provisional first estimate reads 1,000 / Provisional / 1", () => {
  const v = buildTagScopeView({
    scopeType: "TAG_BASED",
    estimatedTagCount: 1000,
    tagScopeStatus: "PROVISIONAL",
    tagScopeRevision: 1,
  });
  assert.deepEqual(rowMap(v.rows), {
    "Estimated Tags": "1,000",
    Status: "Provisional",
    Revision: "1",
  });
});

test("no Tag Scope state is ever blank — every kind renders something", () => {
  const states: TagScopeInputLike[] = [
    { scopeType: "NONE", ...UNSET },
    { scopeType: "TAG_BASED", ...UNSET },
    {
      scopeType: "TAG_BASED",
      estimatedTagCount: 2500,
      tagScopeStatus: "BASELINED",
      tagScopeRevision: 3,
    },
  ];
  for (const s of states) {
    const v = buildTagScopeView(s);
    const visible = v.message.length > 0 || v.rows.length > 0;
    assert.equal(visible, true, `blank panel for ${JSON.stringify(s)}`);
  }
});

test("the panel shows no progress, worked or remaining figure in this phase", () => {
  const v = buildTagScopeView({
    scopeType: "TAG_BASED",
    estimatedTagCount: 2500,
    tagScopeStatus: "BASELINED",
    tagScopeRevision: 3,
  });
  const labels = v.rows.map((r) => r.label.toLowerCase());
  for (const banned of ["progress", "worked", "remaining", "completion", "%"]) {
    assert.equal(labels.some((l) => l.includes(banned)), false, banned);
  }
  // Read-only: no action affordance is described anywhere in the view.
  const text = [v.message, v.hint, ...v.rows.map((r) => r.value)].join(" ").toLowerCase();
  for (const banned of ["revise", "save", "edit scope"]) {
    assert.equal(text.includes(banned), false, banned);
  }
});

type TagScopeInputLike = Parameters<typeof buildTagScopeView>[0];

// ---------- status / count formatting ----------
test("status labels are title-case for display, values stay uppercase", () => {
  assert.equal(TAG_SCOPE_STATUS_LABEL.PROVISIONAL, "Provisional");
  assert.equal(TAG_SCOPE_STATUS_LABEL.BASELINED, "Baselined");
});

test("an unknown or missing status resolves to null, not a fake status", () => {
  assert.equal(resolveTagScopeStatus(null), null);
  assert.equal(resolveTagScopeStatus(undefined), null);
  assert.equal(resolveTagScopeStatus("NOT_STARTED"), null);
  assert.equal(resolveTagScopeStatus("FINALIZED"), null);
  assert.equal(resolveTagScopeStatus("baselined"), null);
  assert.equal(resolveTagScopeStatus("BASELINED"), "BASELINED");
  assert.equal(resolveTagScopeStatus("PROVISIONAL"), "PROVISIONAL");
});

test("tag counts are thousands-separated deterministically", () => {
  assert.equal(formatTagCount(1000), "1,000");
  assert.equal(formatTagCount(2500), "2,500");
  assert.equal(formatTagCount(1), "1");
  assert.equal(formatTagCount(null), NOT_SET_LABEL);
  assert.equal(formatTagCount(undefined), NOT_SET_LABEL);
});

// Test 11 (frontend half) — regression
test("scope type is the only field the classification touches in a submit body", () => {
  const base = toCreateBody(form());
  const tagged = toCreateBody(form({ scope_type: "TAG_BASED" }));
  const differing = Object.keys(tagged).filter(
    (k) => (tagged as Record<string, unknown>)[k] !== (base as Record<string, unknown>)[k],
  );
  assert.deepEqual(differing, ["scope_type"]);
});
