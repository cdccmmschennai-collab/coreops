import assert from "node:assert/strict";
import { test } from "node:test";

import {
  DEFAULT_REVIEW_FILTER,
  REVIEW_FILTERS,
  filterToClassification,
} from "./review.ts";

test("Daily Attendance Review opens on All", () => {
  assert.equal(DEFAULT_REVIEW_FILTER, "all");
  // All sends no classification, so the whole roster comes back.
  assert.equal(filterToClassification(DEFAULT_REVIEW_FILTER), undefined);
});

test("the filter options themselves are unchanged", () => {
  assert.deepEqual(
    REVIEW_FILTERS.map((f) => [f.value, f.label]),
    [
      ["all", "All"],
      ["present", "Present"],
      ["needs_review", "Needs review"],
      ["incomplete", "Punch missing"],
      ["no_record", "No punch"],
    ],
  );
});
