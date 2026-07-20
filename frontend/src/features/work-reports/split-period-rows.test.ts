/**
 * Split-Day row lifecycle rules (see split-period-rows.ts).
 *
 * Split Day allows exactly one activity per working half and has no
 * "add another activity" path at all. These tests pin the pure lifecycle:
 * auto-create, idempotent re-reconciliation, preservation of loaded and
 * malformed rows, and single-half clearing.
 *
 * DOM-level facts (the Add Activity button being absent, the delete icon being
 * hidden, the confirmation dialog rendering) are NOT covered here — the repo
 * has no DOM test runner by design, so those stay manual verification items.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  clearHalf,
  countOfPart,
  hasMalformedHalf,
  indicesOfPart,
  reconcileHalf,
  reconcileHalves,
  validateHalfRowCounts,
  type PartitionedRow,
  type RowPart,
} from "./split-period-rows.ts";

/** A minimal stand-in for a task row: day_part plus a marker to prove identity. */
interface Row extends PartitionedRow {
  day_part: RowPart;
  id: string;
}

let seq = 0;
const emptyRow = (): Row => ({ day_part: "full_day", id: `new-${++seq}` });

const row = (day_part: RowPart, id: string): Row => ({ day_part, id });

const bothWorking = { first_half: true, second_half: true };
const neitherWorking = { first_half: false, second_half: false };

// ── auto-create ────────────────────────────────────────────────────────────

test("working First Half with no rows gets exactly one First-Half row", () => {
  const out = reconcileHalf([], "first_half", true, emptyRow);
  assert.equal(out.length, 1);
  assert.equal(out[0]!.day_part, "first_half");
  assert.equal(countOfPart(out, "first_half"), 1);
});

test("working Second Half with no rows gets exactly one Second-Half row", () => {
  const out = reconcileHalf([], "second_half", true, emptyRow);
  assert.equal(out.length, 1);
  assert.equal(out[0]!.day_part, "second_half");
});

test("Leave -> Working creates exactly one blank row", () => {
  // The half was cleared on the way to Leave; switching back re-creates one.
  const cleared = clearHalf([row("first_half", "a")], "first_half");
  assert.equal(cleared.length, 0);
  const back = reconcileHalf(cleared, "first_half", true, emptyRow);
  assert.equal(back.length, 1);
  assert.equal(back[0]!.day_part, "first_half");
});

test("a non-working half is never given a row", () => {
  const out = reconcileHalves([], neitherWorking, emptyRow);
  assert.equal(out.length, 0);
});

// ── idempotence: the re-render guard ───────────────────────────────────────

test("repeated reconciliation never duplicates a row", () => {
  let rows = reconcileHalves([], bothWorking, emptyRow);
  assert.equal(rows.length, 2);
  for (let i = 0; i < 10; i += 1) {
    rows = reconcileHalves(rows, bothWorking, emptyRow);
  }
  assert.equal(rows.length, 2);
  assert.equal(countOfPart(rows, "first_half"), 1);
  assert.equal(countOfPart(rows, "second_half"), 1);
});

test("a no-op reconciliation returns the SAME array reference", () => {
  // This identity is what lets the form skip a redundant write and is the
  // mechanism preventing duplicate-row creation on re-render.
  const rows = reconcileHalves([], bothWorking, emptyRow);
  assert.equal(reconcileHalves(rows, bothWorking, emptyRow), rows);
  assert.equal(reconcileHalf(rows, "first_half", true, emptyRow), rows);
  assert.equal(reconcileHalf(rows, "first_half", false, emptyRow), rows);
});

// ── preservation ───────────────────────────────────────────────────────────

test("an existing row is preserved, not replaced", () => {
  const existing = [row("first_half", "saved")];
  const out = reconcileHalf(existing, "first_half", true, emptyRow);
  assert.equal(out, existing);
  assert.equal(out[0]!.id, "saved");
});

test("reopening a saved report does not append a second row", () => {
  // One row per working half, as loaded from the API.
  const loaded = [row("first_half", "s1"), row("second_half", "s2")];
  const out = reconcileHalves(loaded, bothWorking, emptyRow);
  assert.equal(out, loaded);
  assert.equal(out.length, 2);
});

test("a malformed two-row half is preserved and never grows a third row", () => {
  const malformed = [
    row("first_half", "m1"),
    row("first_half", "m2"),
    row("second_half", "s"),
  ];
  const out = reconcileHalves(malformed, bothWorking, emptyRow);
  assert.equal(out, malformed);
  assert.equal(countOfPart(out, "first_half"), 2);
  assert.equal(hasMalformedHalf(out), true);
});

test("reconciliation never mutates its input", () => {
  const input = [row("first_half", "a")];
  const snapshot = [...input];
  reconcileHalves(input, bothWorking, emptyRow);
  clearHalf(input, "first_half");
  assert.deepEqual(input, snapshot);
});

// ── isolation: halves and full_day never bleed into each other ─────────────

test("full_day rows are ignored by every half operation", () => {
  const rows = [row("full_day", "f1"), row("full_day", "f2")];
  const out = reconcileHalves(rows, bothWorking, emptyRow);
  // Two halves added, both full_day rows untouched and still first in order.
  assert.equal(out.length, 4);
  assert.deepEqual(
    out.filter((r) => r.day_part === "full_day").map((r) => r.id),
    ["f1", "f2"],
  );
  assert.equal(countOfPart(out, "first_half"), 1);
  assert.equal(countOfPart(out, "second_half"), 1);
  // Clearing a half leaves full_day rows alone.
  assert.equal(countOfPart(clearHalf(out, "first_half"), "full_day"), 2);
});

test("a First-Half row is never moved to Second Half", () => {
  const rows = [row("first_half", "a")];
  // Second Half is working and empty -> it must add its OWN row, not adopt
  // the First-Half one.
  const out = reconcileHalves(rows, bothWorking, emptyRow);
  assert.equal(countOfPart(out, "first_half"), 1);
  assert.equal(countOfPart(out, "second_half"), 1);
  assert.equal(out.find((r) => r.day_part === "first_half")!.id, "a");
});

test("a Second-Half row is never moved to First Half", () => {
  const rows = [row("second_half", "b")];
  const out = reconcileHalves(rows, bothWorking, emptyRow);
  assert.equal(countOfPart(out, "second_half"), 1);
  assert.equal(countOfPart(out, "first_half"), 1);
  assert.equal(out.find((r) => r.day_part === "second_half")!.id, "b");
});

test("indicesOfPart reports positions in the flat array", () => {
  const rows = [
    row("full_day", "f"),
    row("second_half", "s"),
    row("first_half", "a"),
  ];
  assert.deepEqual(indicesOfPart(rows, "first_half"), [2]);
  assert.deepEqual(indicesOfPart(rows, "second_half"), [1]);
});

// ── clearing one half ──────────────────────────────────────────────────────

test("confirmed clear removes only the selected half", () => {
  const rows = [
    row("first_half", "a"),
    row("second_half", "b"),
    row("full_day", "f"),
  ];
  const out = clearHalf(rows, "first_half");
  assert.equal(countOfPart(out, "first_half"), 0);
  assert.equal(countOfPart(out, "second_half"), 1);
  assert.equal(out.find((r) => r.day_part === "second_half")!.id, "b");
  assert.equal(countOfPart(out, "full_day"), 1);
});

test("clearing a malformed half removes all of its rows", () => {
  const rows = [
    row("first_half", "m1"),
    row("first_half", "m2"),
    row("second_half", "b"),
  ];
  const out = clearHalf(rows, "first_half");
  assert.equal(countOfPart(out, "first_half"), 0);
  assert.equal(countOfPart(out, "second_half"), 1);
});

test("clearing an already-empty half is a no-op by reference", () => {
  const rows = [row("second_half", "b")];
  assert.equal(clearHalf(rows, "first_half"), rows);
});

// ── validation ─────────────────────────────────────────────────────────────

test("working half with zero activities is rejected", () => {
  const issues = validateHalfRowCounts([], bothWorking);
  assert.deepEqual(
    issues.map((i) => i.message),
    [
      "First Half must contain exactly one activity.",
      "Second Half must contain exactly one activity.",
    ],
  );
});

test("two activities in First Half are rejected and not reduced", () => {
  const rows = [
    row("first_half", "m1"),
    row("first_half", "m2"),
    row("second_half", "b"),
  ];
  const issues = validateHalfRowCounts(rows, bothWorking);
  assert.equal(issues.length, 1);
  assert.equal(issues[0]!.part, "first_half");
  assert.equal(issues[0]!.kind, "too_many");
  assert.equal(issues[0]!.count, 2);
  assert.equal(
    issues[0]!.message,
    "First Half cannot contain more than one activity.",
  );
  // The rows themselves are untouched — validation reports, it never repairs.
  assert.equal(countOfPart(rows, "first_half"), 2);
});

test("two activities in Second Half are rejected", () => {
  const rows = [
    row("first_half", "a"),
    row("second_half", "m1"),
    row("second_half", "m2"),
  ];
  const issues = validateHalfRowCounts(rows, bothWorking);
  assert.equal(issues.length, 1);
  assert.equal(issues[0]!.part, "second_half");
  assert.equal(
    issues[0]!.message,
    "Second Half cannot contain more than one activity.",
  );
});

test("a non-working half carrying a row is rejected", () => {
  const rows = [row("first_half", "a")];
  const issues = validateHalfRowCounts(rows, {
    first_half: false,
    second_half: false,
  });
  assert.equal(issues.length, 1);
  assert.equal(issues[0]!.kind, "unexpected");
});

test("exactly one activity per working half is valid", () => {
  const rows = [row("first_half", "a"), row("second_half", "b")];
  assert.deepEqual(validateHalfRowCounts(rows, bothWorking), []);
  assert.equal(hasMalformedHalf(rows), false);
});

test("one working half + one leave half is valid", () => {
  const rows = [row("first_half", "a")];
  assert.deepEqual(
    validateHalfRowCounts(rows, { first_half: true, second_half: false }),
    [],
  );
});

test("full_day rows never trigger a Split-Day validation issue", () => {
  const rows = [row("full_day", "f1"), row("full_day", "f2")];
  assert.deepEqual(validateHalfRowCounts(rows, neitherWorking), []);
});
