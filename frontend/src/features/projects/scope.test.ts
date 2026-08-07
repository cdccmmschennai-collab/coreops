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
  DEFAULT_PROJECT_SCOPE_TYPE,
  PROJECT_SCOPE_TYPES,
  PROJECT_SCOPE_TYPE_LABEL,
  resolveScopeType,
  tagScopePlaceholder,
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

// Test 9 — Tag Scope placeholder for a NONE project
test("a non-tag project explains it is not configured and where to change that", () => {
  const p = tagScopePlaceholder("NONE");
  assert.equal(p.title, "This project is not configured as a tag-based project.");
  assert.equal(
    p.description,
    "Change the Project Scope from the Edit Project page to enable tag-scope functionality.",
  );
});

// Test 10 — Tag Scope placeholder for a TAG_BASED project
test("a tag-based project says so and defers configuration to the next phase", () => {
  const p = tagScopePlaceholder("TAG_BASED");
  assert.equal(p.title, "This project is configured as a tag-based project.");
  assert.equal(p.description, "Tag scope configuration will be added in the next phase.");
});

test("neither placeholder offers a tag count or an enable action", () => {
  for (const scope of PROJECT_SCOPE_TYPES) {
    const text = Object.values(tagScopePlaceholder(scope)).join(" ").toLowerCase();
    assert.equal(text.includes("estimated tag"), false);
    assert.equal(text.includes("enable tag scope"), false);
  }
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
