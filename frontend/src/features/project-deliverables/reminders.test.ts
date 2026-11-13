import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  daysRemainingLabel,
  deliverableHref,
  dueInLabel,
  formatDueDate,
  isMyDeliverable,
  LOGIN_REMINDER_DAYS,
  selectLoginReminders,
  isPending,
  selectReminderRows,
  sortReminders,
} from "./reminders.ts";
import type { DeadlineState } from "./types";

interface Row {
  id: string;
  name: string;
  project_code: string;
  target_date: string | null;
  deadline_state: DeadlineState;
  days_remaining: number | null;
}

// Values exactly as the backend would send them (state + days are server-side).
function row(
  id: string,
  state: DeadlineState,
  target: string | null,
  days: number | null,
  code = "4391",
): Row {
  return { id, name: `D-${id}`, project_code: code, target_date: target,
           deadline_state: state, days_remaining: days };
}

const SAMPLE: Row[] = [
  row("later", "on_track", "2026-11-18", 7, "4460"),
  row("soon5", "due_soon", "2026-11-16", 5, "4391"),
  row("done", "completed", "2026-11-01", null, "4120"),
  row("today", "due_today", "2026-11-11", 0, "4120"),
  row("nodate", "no_deadline", null, null, "4500"),
  row("late2", "overdue", "2026-11-09", -2, "4391"),
  row("soon3", "due_soon", "2026-11-14", 3, "4391"),
  row("urgent", "urgent", "2026-11-12", 1, "4460"),
  row("late1", "overdue", "2026-11-10", -1, "4460"),
];

test("priority: overdue, today, 1 day, 2-5 days, later, no deadline", () => {
  const ids = sortReminders(SAMPLE.filter(isPending)).map((r) => r.id);
  assert.deepEqual(ids, ["late2", "late1", "today", "urgent", "soon3", "soon5", "later", "nodate"]);
});

test("within a priority group the earliest deadline comes first", () => {
  const ids = sortReminders([
    row("b", "due_soon", "2026-11-15", 4),
    row("a", "due_soon", "2026-11-13", 2),
    row("c", "due_soon", "2026-11-16", 5),
  ]).map((r) => r.id);
  assert.deepEqual(ids, ["a", "b", "c"]);
});

test("completed deliverables are never pending reminders", () => {
  const { rows, hidden } = selectReminderRows(SAMPLE, 100);
  assert.equal(rows.some((r) => r.id === "done"), false);
  assert.equal(rows.length, SAMPLE.length - 1);
  assert.equal(hidden, 0);
});

test("one flat list in priority order - no attention/later split", () => {
  const { rows } = selectReminderRows(SAMPLE, 100);
  // A 7-day item sits in the same list, right after the 2-5 day items.
  assert.deepEqual(
    rows.map((r) => r.id),
    ["late2", "late1", "today", "urgent", "soon3", "soon5", "later", "nodate"],
  );
});

test("rows are capped at max and the rest are counted as hidden", () => {
  const { rows, hidden } = selectReminderRows(SAMPLE, 6);
  assert.deepEqual(rows.map((r) => r.id), ["late2", "late1", "today", "urgent", "soon3", "soon5"]);
  assert.equal(hidden, 2); // "later" + "nodate"; completed is not counted
});

test("only completed items -> empty list, nothing hidden", () => {
  const { rows, hidden } = selectReminderRows([row("x", "completed", "2026-11-01", null)], 6);
  assert.deepEqual(rows, []);
  assert.equal(hidden, 0);
  assert.deepEqual(selectReminderRows([], 6), { rows: [], hidden: 0 });
});

test("multiple deliverables keep their own project number and detail link", () => {
  const { rows } = selectReminderRows(SAMPLE, 6);
  assert.deepEqual(
    rows.map((r) => [r.id, r.project_code, deliverableHref(r.id)]),
    [["late2", "4391", "/projects/deliverables/late2"],
     ["late1", "4460", "/projects/deliverables/late1"],
     ["today", "4120", "/projects/deliverables/today"],
     ["urgent", "4460", "/projects/deliverables/urgent"],
     ["soon3", "4391", "/projects/deliverables/soon3"],
     ["soon5", "4391", "/projects/deliverables/soon5"]],
  );
});

// No React render harness exists for `node --test`, so the removed card UI is
// guarded at source level: these strings must not come back.
test("card source: no summary tiles, attention message or group headings", () => {
  const src = readFileSync(
    fileURLToPath(new URL("../dashboard/submission-reminders-card.tsx", import.meta.url)),
    "utf8",
  );
  for (const gone of [
    "SummaryTile",
    "Upcoming (1-5 days)",
    "Nothing overdue or due in the next 5 days",
    "need attention",
    "GroupLabel",
    ">Later<",
    "Overdue &amp; next 5 days",
    "summarizeReminders",
    "groupReminders",
  ]) {
    assert.equal(src.includes(gone), false, `card must not contain ${JSON.stringify(gone)}`);
  }
  for (const kept of [
    "Submission Reminders",
    'href="/projects/deliverables"',
    "View all",
    "deliverableHref(d.id)",
    "<DeadlineBadge",
    "daysRemainingLabel(d)",
    "No pending deliverables.",
    "more pending",
    "selectReminderRows(items, MAX_ROWS)",
    // Row data in bold: activity name, project number, due date.
    'text-sm font-semibold text-foreground" title={d.name}',
    'font-mono font-semibold text-foreground">{project}',
    'font-semibold text-foreground">{formatDueDate(d.target_date)}',
  ]) {
    assert.equal(src.includes(kept), true, `card must contain ${JSON.stringify(kept)}`);
  }
});

test("days label mirrors the backend's days_remaining exactly", () => {
  const cases: [DeadlineState, number | null, string][] = [
    ["due_soon", 5, "5 days remaining"],
    ["due_soon", 4, "4 days remaining"],
    ["due_soon", 3, "3 days remaining"],
    ["due_soon", 2, "2 days remaining"],
    ["urgent", 1, "1 day remaining"],
    ["due_today", 0, "Due today"],
    ["overdue", -1, "1 day overdue"],
    ["overdue", -6, "6 days overdue"],
    ["on_track", 7, "7 days remaining"],
    ["no_deadline", null, "No deadline set"],
    ["completed", null, "Completed"],
  ];
  for (const [state, days, label] of cases) {
    assert.equal(daysRemainingLabel({ deadline_state: state, days_remaining: days }), label);
  }
});

test("due date formats without any timezone shift", () => {
  assert.equal(formatDueDate("2026-11-14"), "14 Nov 2026");
  assert.equal(formatDueDate("2026-01-01"), "1 Jan 2026");
  assert.equal(formatDueDate("2026-12-31"), "31 Dec 2026");
  assert.equal(formatDueDate(null), "No deadline");
  assert.equal(formatDueDate("not-a-date"), "not-a-date");
});

test("every reminder links to its exact detail page", () => {
  assert.equal(deliverableHref("abc-123"), "/projects/deliverables/abc-123");
});

// ── login banner (Head + members): planned, due in 0-3 days ──────────────────

test("login reminders keep only planned rows due today to 3 days ahead", () => {
  const items = [
    { id: "a", name: "A", target_date: "2026-11-14", deadline_state: "due_soon" as const, days_remaining: 3 },
    { id: "b", name: "B", target_date: "2026-11-15", deadline_state: "due_soon" as const, days_remaining: 4 },
    { id: "c", name: "C", target_date: "2026-11-11", deadline_state: "due_today" as const, days_remaining: 0 },
    { id: "d", name: "D", target_date: "2026-11-01", deadline_state: "overdue" as const, days_remaining: -10 },
    { id: "e", name: "E", target_date: null, deadline_state: "no_deadline" as const, days_remaining: null },
    { id: "f", name: "F", target_date: "2026-11-12", deadline_state: "completed" as const, days_remaining: null },
    { id: "g", name: "G", target_date: "2026-11-12", deadline_state: "urgent" as const, days_remaining: 1 },
  ];
  assert.deepEqual(selectLoginReminders(items).map((d) => d.id), ["c", "g", "a"]);
  assert.equal(LOGIN_REMINDER_DAYS, 3);
});

test("login reminder wording", () => {
  assert.equal(dueInLabel(0), "Due today");
  assert.equal(dueInLabel(1), "Due tomorrow");
  assert.equal(dueInLabel(3), "Due in 3 days");
});


test("login banner: only the Assignee's own deliverables, plus Head/PM-managed ones", () => {
  const mine = { owner_employee_id: "e1", can_manage: false };
  const someoneElses = { owner_employee_id: "e2", can_manage: false };
  const unassigned = { owner_employee_id: null, can_manage: false };
  assert.equal(isMyDeliverable(mine, "e1"), true);
  assert.equal(isMyDeliverable(someoneElses, "e1"), false);
  assert.equal(isMyDeliverable(unassigned, "e1"), false);
  // Head of the project / PM (backend can_manage) still sees every one.
  assert.equal(isMyDeliverable({ ...someoneElses, can_manage: true }, "e1"), true);
  assert.equal(isMyDeliverable({ ...unassigned, can_manage: true }, null), true);
  // No employee profile: never matches an Assignee.
  assert.equal(isMyDeliverable(unassigned, null), false);

  const src = readFileSync(
    fileURLToPath(new URL("./components/deliverable-due-banner.tsx", import.meta.url)),
    "utf8",
  );
  assert.ok(src.includes("isMyDeliverable(d, employeeId)"));
});