import assert from "node:assert/strict";
import { test } from "node:test";

// Relative .ts imports: the host-Node harness resolves no `@/` alias for values.
import {
  MAX_BULK_DATES,
  MAX_BULK_EMPLOYEES,
  MAX_BULK_PAIRS,
  OUTCOME_LABEL,
  applyBodyFor,
  applyVerdict,
  changedSincePreview,
  checkLimits,
  createApplyOnce,
  datesInRange,
  describeBulkError,
  futureWorkedNotice,
  leaveBlockingRows,
  nonWorkingReason,
  planRangeDates,
  previewBody,
  reasonRequired,
  runPreview,
  tallyResults,
  validateDraft,
  verifyBulkResult,
  type BulkDraft,
  type CalendarOverrides,
} from "./bulk-apply.ts";
import { ATTENDANCE_STATUSES } from "./schemas.ts";
import { can } from "../../lib/rbac.ts";
import type {
  AttendanceBulkApplyBody,
  AttendanceBulkApplyItem,
  AttendanceBulkApplyResult,
  AttendanceStatus,
} from "./types";

const TODAY = "2026-10-14"; // a Wednesday
const NO_CALENDAR: CalendarOverrides = { off: new Map(), working: new Map() };
const E1 = "11111111-1111-1111-1111-111111111111";
const E2 = "22222222-2222-2222-2222-222222222222";
const E3 = "33333333-3333-3333-3333-333333333333";

function draft(over: Partial<BulkDraft> = {}): BulkDraft {
  return {
    mode: "one-employee",
    employeeIds: [E1],
    dates: ["2026-10-15", "2026-10-16"],
    status: "present",
    note: "",
    includeNonWorking: false,
    ...over,
  };
}

/** What the server returns for a body: one item per pair, in request order. */
function serverResult(
  body: AttendanceBulkApplyBody,
  outcomeFor: (emp: string, date: string) => Partial<AttendanceBulkApplyItem> = () => ({}),
): AttendanceBulkApplyResult {
  const results: AttendanceBulkApplyItem[] = [];
  for (const employee_id of body.employee_ids) {
    for (const attendance_date of body.dates) {
      results.push({
        employee_id,
        employee_code: "EMP",
        employee_name: "Someone",
        attendance_date,
        outcome: "created",
        reason_code: null,
        message: null,
        record_id: null,
        previous_status: null,
        status: body.status,
        warnings: [],
        ...outcomeFor(employee_id, attendance_date),
      });
    }
  }
  const t = tallyResults(results);
  return {
    dry_run: body.dry_run,
    bulk_action_id: body.dry_run ? null : "aaaaaaaa-0000-0000-0000-000000000000",
    status: body.status,
    summary: {
      created: t.created,
      updated: t.updated,
      unchanged: t.unchanged,
      protected: t.protected,
      rejected: t.rejected,
    },
    results,
  };
}

/** A fake transport that records every body and answers like the server. */
function recordingSend(
  answer: (body: AttendanceBulkApplyBody) => unknown = (b) => serverResult(b),
) {
  const calls: AttendanceBulkApplyBody[] = [];
  const send = async (body: AttendanceBulkApplyBody) => {
    calls.push(body);
    return answer(body);
  };
  return { calls, send };
}

// ── request payload ──────────────────────────────────────────────────────────

test("preview body carries the backend's exact fields and is always a dry run", () => {
  const body = previewBody(
    draft({ note: "  Planned site visit  ", includeNonWorking: true }),
  );
  assert.deepEqual(body, {
    employee_ids: [E1],
    dates: ["2026-10-15", "2026-10-16"],
    status: "present",
    note: "Planned site visit",
    include_non_working: true,
    dry_run: true,
  });
});

test("the body never carries check-in/check-out - even for future dates", () => {
  const body = previewBody(draft({ dates: ["2026-12-01"] }));
  for (const key of Object.keys(body)) {
    assert.ok(!/check_in|check_out|time/i.test(key), `unexpected time field ${key}`);
  }
  for (const key of Object.keys(applyBodyFor(body))) {
    assert.ok(!/check_in|check_out|time/i.test(key), `unexpected time field ${key}`);
  }
});

test("an empty reason is sent as null, not as an empty string", () => {
  assert.equal(previewBody(draft({ note: "   " })).note, null);
});

test("duplicates are dropped and dates sorted before sending", () => {
  const body = previewBody(
    draft({ employeeIds: [E2, E1, E2], dates: ["2026-10-16", "2026-10-15", "2026-10-16"] }),
  );
  assert.deepEqual(body.employee_ids, [E2, E1]);
  assert.deepEqual(body.dates, ["2026-10-15", "2026-10-16"]);
});

test("apply sends the previewed request unchanged except dry_run=false", () => {
  const previewed = previewBody(draft({ note: "x" }));
  const applied = applyBodyFor(previewed);
  assert.equal(applied.dry_run, false);
  assert.deepEqual({ ...applied, dry_run: true }, previewed);
  assert.equal(previewed.dry_run, true, "the preview body is not mutated");
});

test("all seven canonical statuses build a request", () => {
  assert.equal(ATTENDANCE_STATUSES.length, 7);
  for (const status of ATTENDANCE_STATUSES) {
    assert.equal(previewBody(draft({ status })).status, status);
    assert.deepEqual(validateDraft(draft({ status }), TODAY), []);
  }
});

// ── Mode A: one employee, a range of dates ──────────────────────────────────

test("a range expands to every date, inclusive, across month ends", () => {
  assert.deepEqual(datesInRange("2026-10-30", "2026-11-02"), [
    "2026-10-30",
    "2026-10-31",
    "2026-11-01",
    "2026-11-02",
  ]);
  assert.deepEqual(datesInRange("2026-10-14", "2026-10-14"), ["2026-10-14"]);
});

test("a backwards, invalid or enormous range is not expanded", () => {
  assert.equal(datesInRange("2026-10-15", "2026-10-14"), null);
  assert.equal(datesInRange("2026-02-30", "2026-03-02"), null);
  assert.equal(datesInRange("", "2026-10-14"), null);
  assert.equal(datesInRange("2024-01-01", "2026-12-31"), null);
});

test("non-working days follow the office week, not every Saturday", () => {
  // October 2026: Sat 3 (1st), Sat 10 (2nd), Sat 17 (3rd), Sat 24 (4th), Sat 31 (5th).
  assert.equal(nonWorkingReason("2026-10-03", NO_CALENDAR), null);
  assert.equal(nonWorkingReason("2026-10-10", NO_CALENDAR), "2nd Saturday");
  assert.equal(nonWorkingReason("2026-10-17", NO_CALENDAR), null);
  assert.equal(nonWorkingReason("2026-10-24", NO_CALENDAR), "4th Saturday");
  assert.equal(nonWorkingReason("2026-10-31", NO_CALENDAR), null);
  assert.equal(nonWorkingReason("2026-10-11", NO_CALENDAR), "Sunday");
  assert.equal(nonWorkingReason("2026-10-14", NO_CALENDAR), null);
});

test("calendar overrides: a working day wins, a holiday closes a weekday", () => {
  const cal: CalendarOverrides = {
    off: new Map([["2026-10-14", "Diwali"], ["2026-10-11", "Overlap"]]),
    working: new Map([["2026-10-11", "Make-up day"]]),
  };
  assert.equal(nonWorkingReason("2026-10-14", cal), "Holiday - Diwali");
  assert.equal(nonWorkingReason("2026-10-11", cal), null);
});

test("non-working days are skipped by default - and say so", () => {
  const plan = planRangeDates({
    dates: datesInRange("2026-10-09", "2026-10-12")!, // Fri, 2nd Sat, Sun, Mon
    excluded: new Set(),
    includeNonWorking: false,
    calendar: NO_CALENDAR,
  });
  assert.deepEqual(
    plan.map((p) => [p.date, p.included, p.skipNote]),
    [
      ["2026-10-09", true, null],
      ["2026-10-10", false, "Skipped - non-working day (2nd Saturday)"],
      ["2026-10-11", false, "Skipped - non-working day (Sunday)"],
      ["2026-10-12", true, null],
    ],
  );
});

test("including non-working days puts them back in the request", () => {
  const plan = planRangeDates({
    dates: datesInRange("2026-10-09", "2026-10-12")!,
    excluded: new Set(),
    includeNonWorking: true,
    calendar: NO_CALENDAR,
  });
  assert.ok(plan.every((p) => p.included));
  const body = previewBody(
    draft({ dates: plan.filter((p) => p.included).map((p) => p.date), includeNonWorking: true }),
  );
  assert.equal(body.include_non_working, true);
  assert.equal(body.dates.length, 4);
});

test("a date the PM excludes stays listed as excluded and is not sent", () => {
  const plan = planRangeDates({
    dates: ["2026-10-15", "2026-10-16"],
    excluded: new Set(["2026-10-16"]),
    includeNonWorking: false,
    calendar: NO_CALENDAR,
  });
  assert.deepEqual(
    plan.map((p) => [p.date, p.included, p.skipNote]),
    [
      ["2026-10-15", true, null],
      ["2026-10-16", false, "Excluded by you"],
    ],
  );
});

test("Mode A over the 62-date limit is refused with an explanation, not truncated", () => {
  const dates = datesInRange("2026-11-01", "2027-01-15")!; // 76 days
  const errors = validateDraft(draft({ dates }), TODAY);
  assert.ok(errors.some((e) => e.includes(`at most ${MAX_BULK_DATES}`)), errors.join("\n"));
  // The draft is untouched - nothing was dropped to fit.
  assert.equal(dates.length, 76);
});

// ── Mode B: many employees, one date ────────────────────────────────────────

test("Mode B sends every selected employee on the one date with one status", () => {
  const body = previewBody(
    draft({ mode: "one-date", employeeIds: [E1, E2, E3], dates: ["2026-10-20"], status: "holiday" }),
  );
  assert.deepEqual(body.employee_ids, [E1, E2, E3]);
  assert.deepEqual(body.dates, ["2026-10-20"]);
  assert.equal(body.status, "holiday");
});

test("an excluded employee is simply not in the request", () => {
  const selected = new Set([E1, E2, E3]);
  selected.delete(E2);
  const body = previewBody(
    draft({ mode: "one-date", employeeIds: [...selected], dates: ["2026-10-20"] }),
  );
  assert.ok(!body.employee_ids.includes(E2));
});

test("Mode B over 200 employees is refused with an explanation", () => {
  const ids = Array.from({ length: 201 }, (_, i) => `emp-${i}`);
  const errors = validateDraft(
    draft({ mode: "one-date", employeeIds: ids, dates: ["2026-10-20"] }),
    TODAY,
  );
  assert.ok(errors.some((e) => e.includes(`at most ${MAX_BULK_EMPLOYEES}`)));
});

test("the 500 employee-day limit is checked too", () => {
  assert.deepEqual(checkLimits(10, 50), []);
  assert.ok(checkLimits(10, 51).some((e) => e.includes(`at most ${MAX_BULK_PAIRS}`)));
});

// ── validation and attendance rules ─────────────────────────────────────────

test("basic inputs are required, with mode-specific wording", () => {
  const a = validateDraft(draft({ employeeIds: [], dates: [], status: "" }), TODAY);
  assert.ok(a.includes("Select an employee."));
  assert.ok(a.some((e) => e.startsWith("No dates are included")));
  assert.ok(a.includes("Choose the attendance status to apply."));
  const b = validateDraft(draft({ mode: "one-date", employeeIds: [], dates: [] }), TODAY);
  assert.ok(b.includes("Select at least one employee."));
  assert.ok(b.includes("Select an attendance date."));
});

test("a past date requires a reason; today and the future do not", () => {
  assert.ok(reasonRequired(["2026-10-13"], TODAY));
  assert.ok(!reasonRequired([TODAY, "2026-10-15"], TODAY));
  const past = validateDraft(draft({ dates: ["2026-10-12", "2026-10-15"] }), TODAY);
  assert.ok(past.some((e) => e.includes("reason is required") && e.includes("1 of the 2")));
  assert.deepEqual(
    validateDraft(draft({ dates: ["2026-10-12"], note: "Missed punches" }), TODAY),
    [],
  );
  assert.deepEqual(validateDraft(draft({ dates: [TODAY] }), TODAY), []);
});

test("a whitespace-only reason does not satisfy the rule", () => {
  const errors = validateDraft(draft({ dates: ["2026-10-01"], note: "   " }), TODAY);
  assert.ok(errors.some((e) => e.includes("reason is required")));
});

test("future Present / Half day warns that it blocks leave", () => {
  for (const status of ["present", "half_day"] as AttendanceStatus[]) {
    const note = futureWorkedNotice(status, ["2026-10-20", "2026-10-21"], TODAY);
    assert.ok(note && /blocks leave/.test(note), String(note));
  }
  // Not for other statuses, and not for past/today dates.
  assert.equal(futureWorkedNotice("leave", ["2026-10-20"], TODAY), null);
  assert.equal(futureWorkedNotice("present", ["2026-10-13", TODAY], TODAY), null);
});

test("the server's pending-leave warnings are picked out for the preview", () => {
  const rows = serverResult(previewBody(draft()), (_e, d) =>
    d === "2026-10-16"
      ? {
          warnings: [
            {
              code: "pending_leave_request",
              message: "A pending leave request covers this day.",
            },
          ],
        }
      : {},
  ).results;
  assert.deepEqual(
    leaveBlockingRows(rows).map((r) => r.attendance_date),
    ["2026-10-16"],
  );
});

test("unauthorized users have no attendance write capability", () => {
  assert.equal(can("employee", "attendance.manage"), false);
  assert.equal(can(undefined, "attendance.manage"), false);
  assert.equal(can("project_manager", "attendance.manage"), true);
});

// ── response verification ───────────────────────────────────────────────────

test("a complete, consistent response is accepted", () => {
  const body = previewBody(draft({ employeeIds: [E1, E2] }));
  const v = verifyBulkResult(serverResult(body), body);
  assert.ok(v.ok);
});

test("a response missing a pair is refused - nothing is invented for it", () => {
  const body = previewBody(draft({ employeeIds: [E1, E2] }));
  const res = serverResult(body);
  res.results.pop();
  const v = verifyBulkResult(res, body);
  assert.equal(v.ok, false);
});

test("malformed responses are refused", () => {
  const body = previewBody(draft());
  const good = serverResult(body);
  const cases: unknown[] = [
    null,
    "ok",
    { ...good, results: undefined },
    { ...good, dry_run: false }, // an apply answer to a preview
    { ...good, status: "absent" },
    { ...good, results: good.results.map((r, i) => (i === 0 ? { ...r, outcome: "saved" } : r)) },
    { ...good, results: good.results.map((r, i) => (i === 0 ? { ...r, employee_id: E3 } : r)) },
    { ...good, results: [good.results[0], good.results[0]] },
    { ...good, summary: { ...good.summary, created: good.summary.created + 1 } },
  ];
  for (const raw of cases) {
    assert.equal(verifyBulkResult(raw, body).ok, false, JSON.stringify(raw)?.slice(0, 80));
  }
});

test("an apply response without its action id is refused", () => {
  const body = applyBodyFor(previewBody(draft()));
  const res = serverResult(body);
  assert.ok(verifyBulkResult(res, body).ok);
  assert.equal(verifyBulkResult({ ...res, bulk_action_id: null }, body).ok, false);
});

// ── workflow: preview, apply, results ───────────────────────────────────────

test("preview sends exactly one dry-run request and never an apply", async () => {
  const { calls, send } = recordingSend();
  const out = await runPreview(send, previewBody(draft()));
  assert.equal(out.kind, "result");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].dry_run, true);
});

test("preview refuses to send a non-dry-run body", async () => {
  const { calls, send } = recordingSend();
  await assert.rejects(runPreview(send, applyBodyFor(previewBody(draft()))));
  assert.equal(calls.length, 0);
});

test("apply is only reachable through a confirmed preview body", async () => {
  const { calls, send } = recordingSend();
  const preview = await runPreview(send, previewBody(draft()));
  assert.equal(preview.kind, "result");
  const apply = createApplyOnce(send);
  const out = await apply(preview.request);
  assert.equal(out?.kind, "result");
  assert.deepEqual(
    calls.map((c) => c.dry_run),
    [true, false],
  );
});

test("a double confirm sends only one apply request", async () => {
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  const { calls, send } = recordingSend();
  const slowSend = async (body: AttendanceBulkApplyBody) => {
    await gate;
    return send(body);
  };
  const apply = createApplyOnce(slowSend);
  const body = previewBody(draft());
  const first = apply(body);
  const second = apply(body); // clicked again while the first is in flight
  release();
  assert.equal((await first)?.kind, "result");
  assert.equal(await second, null);
  assert.equal(calls.length, 1);
});

test("a timed-out or dropped apply is reported as ambiguous and never retried", async () => {
  let attempts = 0;
  const failing = async () => {
    attempts += 1;
    throw { code: "network_error", status: 0, message: "Could not reach the server." };
  };
  const apply = createApplyOnce(failing);
  const out = await apply(previewBody(draft()));
  assert.equal(out?.kind, "error");
  if (out?.kind === "error") {
    assert.equal(out.error.ambiguous, true);
    assert.match(out.error.message, /may already have been saved/);
    assert.match(out.error.message, /not retried/);
  }
  // Calling again does nothing - no automatic or accidental retry.
  assert.equal(await apply(previewBody(draft())), null);
  assert.equal(attempts, 1);
});

test("a malformed apply response is not shown as success", async () => {
  const { send } = recordingSend((b) => ({ ...serverResult(b), results: [] }));
  const out = await createApplyOnce(send)(previewBody(draft()));
  assert.equal(out?.kind, "unverified");
});

test("partial success is reported as partial, with totals from the rows", async () => {
  const body = previewBody(draft({ employeeIds: [E1, E2], dates: ["2026-10-15"] }));
  const { send } = recordingSend((b) =>
    serverResult(b, (emp) =>
      emp === E2
        ? {
            outcome: "protected",
            reason_code: "leave_approval",
            message:
              "Written by an approved leave request. Change it through the leave request (cancel or edit), not here.",
            status: "leave",
          }
        : { outcome: "updated", previous_status: "absent" },
    ),
  );
  const out = await createApplyOnce(send)(body);
  assert.equal(out?.kind, "result");
  if (out?.kind !== "result") return;
  const t = tallyResults(out.result.results);
  assert.deepEqual(
    [t.total, t.updated, t.protected, t.changed, t.refused],
    [2, 1, 1, 1, 1],
  );
  assert.equal(applyVerdict(t), "partial");
  // The protected row keeps the server's own reason for the PM to read.
  const protectedRow = out.result.results.find((r) => r.outcome === "protected");
  assert.match(protectedRow?.message ?? "", /approved leave request/);
  assert.equal(OUTCOME_LABEL.applied.protected, "Not changed - leave");
});

test("verdicts never call a refusal a success", () => {
  const t = (o: Partial<Record<"created" | "updated" | "unchanged" | "protected" | "rejected", number>>) =>
    tallyResults(
      Object.entries(o).flatMap(([outcome, n]) =>
        Array.from({ length: n ?? 0 }, () => ({ outcome: outcome as AttendanceBulkApplyItem["outcome"] })),
      ),
    );
  assert.equal(applyVerdict(t({ created: 3 })), "all_saved");
  assert.equal(applyVerdict(t({ created: 2, unchanged: 1 })), "all_saved");
  assert.equal(applyVerdict(t({ created: 2, rejected: 1 })), "partial");
  assert.equal(applyVerdict(t({ rejected: 2 })), "nothing_saved");
  assert.equal(applyVerdict(t({ unchanged: 2 })), "nothing_to_change");
});

test("rows whose outcome changed between preview and save are counted", () => {
  const body = previewBody(draft({ employeeIds: [E1, E2], dates: ["2026-10-15"] }));
  const preview = serverResult(body).results;
  const applied = serverResult(applyBodyFor(body), (emp) =>
    emp === E2 ? { outcome: "rejected", reason_code: "concurrent_change" } : {},
  ).results;
  assert.equal(changedSincePreview(preview, applied), 1);
});

// ── error display ───────────────────────────────────────────────────────────

test("a 422 limit refusal shows the server's message, not internals", () => {
  const view = describeBulkError(
    {
      code: "validation_error",
      status: 422,
      message: "Request validation failed.",
      details: {
        errors: [{ msg: "Value error, A bulk action can cover at most 500 employee-days." }],
      },
    },
    "preview",
  );
  assert.equal(view.ambiguous, false);
  assert.equal(
    view.message,
    "The server refused the request: A bulk action can cover at most 500 employee-days.",
  );
});

test("forbidden and server errors are shown safely", () => {
  assert.match(describeBulkError({ status: 403, code: "forbidden" }, "apply").message, /permission/);
  const preview500 = describeBulkError({ status: 500, message: "Traceback ..." }, "preview");
  assert.ok(!preview500.message.includes("Traceback"));
  assert.match(preview500.message, /Nothing was saved/);
  const apply500 = describeBulkError({ status: 500 }, "apply");
  assert.equal(apply500.ambiguous, true);
  // A thrown non-error (e.g. a string) never leaks into the message.
  assert.ok(!describeBulkError("boom secret", "apply").message.includes("secret"));
});

test("a preview that fails is reported, with no apply attempted", async () => {
  const calls: AttendanceBulkApplyBody[] = [];
  const out = await runPreview(async (b) => {
    calls.push(b);
    throw { status: 503 };
  }, previewBody(draft()));
  assert.equal(out.kind, "error");
  assert.equal(calls.length, 1);
  assert.ok(calls.every((c) => c.dry_run === true));
});
