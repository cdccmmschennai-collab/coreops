import assert from "node:assert/strict";
import { test } from "node:test";

// Relative .ts import: the host-Node harness resolves no `@/` alias for values.
import {
  allowedTabKeys,
  attendanceTabs,
  resolveTab,
  type TabOptions,
} from "./tabs.ts";

const EMPLOYEE: TabOptions = { canManage: false, correctionsEnabled: false };
const MANAGER: TabOptions = { canManage: true, correctionsEnabled: false };

const labels = (o: TabOptions) => attendanceTabs(o).map((t) => t.label);

// ── the label this fix exists for ──────────────────────────────────────────

test("the old History label is gone for every role and flag combination", () => {
  for (const canManage of [true, false]) {
    for (const correctionsEnabled of [true, false]) {
      const rendered = labels({ canManage, correctionsEnabled });
      assert.ok(
        !rendered.includes("History"),
        `"History" still rendered for ${JSON.stringify({ canManage, correctionsEnabled })}`,
      );
    }
  }
});

test("the tab reads Records", () => {
  assert.ok(labels(EMPLOYEE).includes("Records"));
  const tab = attendanceTabs(EMPLOYEE).find((t) => t.label === "Records");
  assert.equal(tab?.value, "history");
});

test("the URL key stays `history` so existing links keep working", () => {
  // /attendance?tab=history is bookmarkable and already in the wild. Renaming
  // the label must not 404 it into Calendar.
  assert.equal(resolveTab("history", EMPLOYEE), "history");
  assert.ok(allowedTabKeys(EMPLOYEE).includes("history"));
});

test("Records is not labelled as the biometric daily review", () => {
  // That workflow is a later phase and will arrive as its own tab. This one
  // renders the manual attendance_records list.
  for (const label of labels(MANAGER)) {
    assert.ok(!/review/i.test(label), `unexpected review-flavoured label: ${label}`);
  }
});

// ── everything else must be untouched ──────────────────────────────────────

test("the employee tab row is Calendar, Records, Leave, Holidays", () => {
  assert.deepEqual(labels(EMPLOYEE), ["Calendar", "Records", "Leave", "Holidays"]);
});

test("a manager also sees Leave Balance, in place", () => {
  assert.deepEqual(labels(MANAGER), [
    "Calendar",
    "Records",
    "Leave",
    "Leave Balance",
    "Holidays",
  ]);
});

test("Leave Balance is manager-only", () => {
  assert.ok(!allowedTabKeys(EMPLOYEE).includes("leave-balance"));
  assert.ok(allowedTabKeys(MANAGER).includes("leave-balance"));
});

test("Corrections appears only behind its feature flag", () => {
  assert.ok(!labels(MANAGER).includes("Corrections"));
  const flagged = attendanceTabs({ canManage: true, correctionsEnabled: true });
  assert.deepEqual(flagged.map((t) => t.label), [
    "Calendar",
    "Records",
    "Leave",
    "Leave Balance",
    "Corrections",
    "Holidays",
  ]);
});

test("no other tab was renamed", () => {
  // Guards the "do not rename unrelated functionality" rule: every key still
  // carries the wording it had before, `history` excepted.
  const byKey = Object.fromEntries(
    attendanceTabs({ canManage: true, correctionsEnabled: true }).map((t) => [
      t.value,
      t.label,
    ]),
  );
  assert.equal(byKey.calendar, "Calendar");
  assert.equal(byKey.leave, "Leave");
  assert.equal(byKey["leave-balance"], "Leave Balance");
  assert.equal(byKey.corrections, "Corrections");
  assert.equal(byKey.holidays, "Holidays");
});

// ── URL resolution behaviour is unchanged ──────────────────────────────────

test("an unknown or stale tab falls back to Calendar", () => {
  assert.equal(resolveTab("nope", EMPLOYEE), "calendar");
  assert.equal(resolveTab("", EMPLOYEE), "calendar");
  // "records" is the LABEL, never a URL key - it must not resolve.
  assert.equal(resolveTab("records", EMPLOYEE), "calendar");
});

test("a manager-only tab requested by a non-manager falls back to Calendar", () => {
  assert.equal(resolveTab("leave-balance", EMPLOYEE), "calendar");
  assert.equal(resolveTab("leave-balance", MANAGER), "leave-balance");
});

test("a flagged-off tab is not reachable by typing its key", () => {
  assert.equal(resolveTab("corrections", MANAGER), "calendar");
  assert.equal(
    resolveTab("corrections", { canManage: true, correctionsEnabled: true }),
    "corrections",
  );
});

test("the PM dashboard deep link /attendance?tab=leave still resolves", () => {
  assert.equal(resolveTab("leave", EMPLOYEE), "leave");
});

test("rendered tabs and reachable keys can never disagree", () => {
  for (const canManage of [true, false]) {
    for (const correctionsEnabled of [true, false]) {
      const options = { canManage, correctionsEnabled };
      assert.deepEqual(
        allowedTabKeys(options),
        attendanceTabs(options).map((t) => t.value),
      );
    }
  }
});
