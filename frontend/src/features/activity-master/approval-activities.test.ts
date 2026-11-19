/**
 * Pure-logic tests for the Approval Activities picker.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { groupApprovalCandidates, isReworkCandidate } from "./approval-activities.ts";
import type { SubActivityFlat } from "./types";

function sub(
  id: string,
  name: string,
  activity: [string, string],
  requires_pm_approval = false,
): SubActivityFlat {
  return {
    id,
    activity_id: activity[0],
    activity_name: activity[1],
    name,
    benchmark_type: null,
    benchmark_value: null,
    benchmark_period_days: null,
    benchmark_unit_note: null,
    benchmark_remarks: null,
    relevant_count_field: null,
    is_active: true,
    requires_pm_approval,
  };
}

const INST: [string, string] = ["a1", "INSTRUMENT ENGINEERING"];
const CABLE: [string, string] = ["a2", "CABLE SCHEDULE"];

const DATA = [
  sub("s1", "Instrument Design", INST),
  sub("s2", "Instrument Rework", INST),
  sub("s3", "Instrument Modification", INST),
  sub("s4", "Instrument Rework - Revision 2", INST, true),
  sub("s5", "CABLE-REWORK", CABLE),
  sub("s6", "Cable Routing", CABLE),
];

test("rework detection is a search hint with word-start matching", () => {
  assert.equal(isReworkCandidate("Instrument Rework"), true);
  assert.equal(isReworkCandidate("Re-work drawings"), true);
  assert.equal(isReworkCandidate("re work"), true);
  assert.equal(isReworkCandidate("CABLE-REWORK"), true);
  assert.equal(isReworkCandidate("Fireworks"), false);
  assert.equal(isReworkCandidate("Instrument Design"), false);
});

test("already-configured sub-activities are never offered again", () => {
  const ids = groupApprovalCandidates(DATA, "").flatMap((g) => g.subs.map((s) => s.id));
  assert.ok(!ids.includes("s4"));
  assert.equal(ids.length, 5);
});

test("term matching the parent shows all its remaining sub-activities", () => {
  const groups = groupApprovalCandidates(DATA, "instrument eng");
  assert.equal(groups.length, 1);
  assert.deepEqual(groups[0].subs.map((s) => s.id), ["s1", "s2", "s3"]);
});

test("term matching a sub-activity keeps only matching children, grouped", () => {
  const groups = groupApprovalCandidates(DATA, "rework");
  assert.deepEqual(
    groups.map((g) => [g.activityName, g.subs.map((s) => s.id)]),
    [
      ["INSTRUMENT ENGINEERING", ["s2"]],
      ["CABLE SCHEDULE", ["s5"]],
    ],
  );
});

test("reworkOnly narrows to rework-looking names", () => {
  const groups = groupApprovalCandidates(DATA, "", { reworkOnly: true });
  assert.deepEqual(groups.flatMap((g) => g.subs.map((s) => s.id)), ["s2", "s5"]);
});
