import assert from "node:assert/strict";
import { test } from "node:test";
import {
  LEAVE_HALF_DAY_LABEL,
  LEAVE_TYPE_CHOICES,
  LEAVE_TYPE_CHOICE_LABEL,
  isHalfDayChoice,
  leaveClassificationNote,
  leaveCreateBody,
} from "./types.ts";
import type { LeaveFormValues, LeaveTypeChoice } from "./types.ts";

// The Leave type dropdown (Phase 2). What is under test is the pure part: which
// options exist, what they are called, and what body each one turns the form
// into. The dialog itself is a thin shell over `leaveCreateBody`.

function values(overrides: Partial<LeaveFormValues> = {}): LeaveFormValues {
  return {
    leave_type: "normal",
    start_date: "",
    end_date: "",
    half_day_date: "",
    reason: "",
    ...overrides,
  };
}

// ---------- the four options and their exact wording ------------------------

test("the dropdown offers exactly four options, in order", () => {
  assert.deepEqual(LEAVE_TYPE_CHOICES, [
    "normal",
    "special",
    "first_half",
    "second_half",
  ]);
});

test("the half-day options read exactly as the product specified", () => {
  assert.equal(LEAVE_TYPE_CHOICE_LABEL.first_half, "Half Day (First)");
  assert.equal(LEAVE_TYPE_CHOICE_LABEL.second_half, "Half Day (Second)");
});

test("the wording the backend renders is the same wording", () => {
  // Must stay identical to `HALF_DAY_PERIOD_LABELS` in
  // backend/app/modules/leave/models.py.
  assert.equal(LEAVE_HALF_DAY_LABEL.first_half, "Half Day (First)");
  assert.equal(LEAVE_HALF_DAY_LABEL.second_half, "Half Day (Second)");
});

test("no option shows a technical name, a dash or the superseded spelling", () => {
  for (const choice of LEAVE_TYPE_CHOICES) {
    const label = LEAVE_TYPE_CHOICE_LABEL[choice];
    assert.ok(!label.includes("_"), label);
    // The house rule: never an em or en dash. And the Phase 1 spelling
    // ("Half Day · 1st Half") was replaced outright - neither half of it may
    // drift back.
    assert.ok(!label.includes("—") && !label.includes("–"), label);
    assert.ok(!label.includes("·"), label);
    assert.ok(!label.includes("1st") && !label.includes("2nd"), label);
  }
});

test("Normal and Special keep the names the frozen field always showed", () => {
  assert.equal(LEAVE_TYPE_CHOICE_LABEL.normal, "Normal");
  assert.equal(LEAVE_TYPE_CHOICE_LABEL.special, "Special");
});

// ---------- which options ask for one date ----------------------------------

test("only the two half-day options are single-date", () => {
  assert.equal(isHalfDayChoice("first_half"), true);
  assert.equal(isHalfDayChoice("second_half"), true);
  assert.equal(isHalfDayChoice("normal"), false);
  assert.equal(isHalfDayChoice("special"), false);
});

// ---------- Normal / Special build the body they always did -----------------

test("a Normal request sends the existing three keys and nothing else", () => {
  const body = leaveCreateBody(
    values({ leave_type: "normal", start_date: "2027-03-03", end_date: "2027-03-05", reason: "Trip" }),
  );

  assert.deepEqual(body, {
    start_date: "2027-03-03",
    end_date: "2027-03-05",
    reason: "Trip",
  });
  assert.ok(!("half_day_period" in body));
});

test("a Special request is the same body - the two differ only on the server", () => {
  // Normal/Special is DERIVED from the working days the dates cost. The
  // dropdown picks the shape of the form, never the classification, so these
  // two options must produce byte-identical payloads.
  const dates = { start_date: "2027-03-01", end_date: "2027-03-20", reason: "Long" };
  const normal = leaveCreateBody(values({ leave_type: "normal", ...dates }));
  const special = leaveCreateBody(values({ leave_type: "special", ...dates }));

  assert.deepEqual(normal, special);
});

test("multi-day full-day leave is untouched", () => {
  const body = leaveCreateBody(
    values({ leave_type: "special", start_date: "2027-03-01", end_date: "2027-03-31" }),
  );

  assert.equal(body.start_date, "2027-03-01");
  assert.equal(body.end_date, "2027-03-31");
  assert.notEqual(body.start_date, body.end_date);
});

test("an empty reason is sent as null, as it always was", () => {
  const body = leaveCreateBody(
    values({ start_date: "2027-03-03", end_date: "2027-03-03", reason: "   " }),
  );

  assert.equal(body.reason, null);
});

// ---------- a half day is ONE date --------------------------------------

test("Half Day (First) sends one date on both ends, plus the half", () => {
  const body = leaveCreateBody(
    values({ leave_type: "first_half", half_day_date: "2027-03-03", reason: "Clinic" }),
  );

  assert.deepEqual(body, {
    start_date: "2027-03-03",
    end_date: "2027-03-03",
    half_day_period: "first_half",
    reason: "Clinic",
  });
});

test("Half Day (Second) sends the other half, otherwise identically", () => {
  const body = leaveCreateBody(
    values({ leave_type: "second_half", half_day_date: "2027-03-03", reason: "Clinic" }),
  );

  assert.equal(body.half_day_period, "second_half");
  assert.equal(body.start_date, body.end_date);
});

test("a range typed before switching to a half day cannot leak into it", () => {
  // The two date shapes live side by side in the form state so that toggling
  // the dropdown does not destroy what was typed. That makes this the important
  // case: the From/To pair must be ignored ENTIRELY by a half-day request, or a
  // "half day" would reach the API spanning three days.
  const body = leaveCreateBody(
    values({
      leave_type: "first_half",
      start_date: "2027-03-01",
      end_date: "2027-03-03",
      half_day_date: "2027-03-10",
    }),
  );

  assert.equal(body.start_date, "2027-03-10");
  assert.equal(body.end_date, "2027-03-10");
});

test("the half sent is the option itself, so the two cannot drift apart", () => {
  for (const choice of ["first_half", "second_half"] as const) {
    const body = leaveCreateBody(values({ leave_type: choice, half_day_date: "2027-03-03" }));
    assert.equal(body.half_day_period, choice);
  }
});

// ---------- the derived classification is still the backend's ---------------

test("the note reports the server's answer for the dates in the form", () => {
  assert.equal(
    leaveClassificationNote("normal", { working_days: 3, classification: "normal" }),
    "These dates cost 3 working days - this will be filed as Normal Leave.",
  );
});

test("picking Normal for a long range is corrected on screen, not silently", () => {
  // THE WHOLE POINT OF THE NOTE. The dropdown is not an override: a fortnight
  // is filed as Special whatever was picked, and the employee is told so while
  // the form is still open.
  assert.equal(
    leaveClassificationNote("normal", { working_days: 11, classification: "special" }),
    "These dates cost 11 working days - this will be filed as Special Leave.",
  );
});

test("one working day is singular", () => {
  assert.equal(
    leaveClassificationNote("normal", { working_days: 1, classification: "normal" }),
    "These dates cost 1 working day - this will be filed as Normal Leave.",
  );
});

test("there is no note before any dates are chosen", () => {
  assert.equal(leaveClassificationNote("normal", undefined), null);
});

test("a half day gets no note - it is one day and already says what it is", () => {
  const preview = { working_days: 1, classification: "normal" } as const;
  assert.equal(leaveClassificationNote("first_half", preview), null);
  assert.equal(leaveClassificationNote("second_half", preview), null);
});

// ---------- every option is a complete, buildable request -------------------

test("all four options produce a body with matching-or-ordered dates", () => {
  const built = LEAVE_TYPE_CHOICES.map((choice: LeaveTypeChoice) =>
    leaveCreateBody(
      values({
        leave_type: choice,
        start_date: "2027-03-03",
        end_date: "2027-03-05",
        half_day_date: "2027-03-03",
      }),
    ),
  );

  for (const body of built) {
    assert.ok(body.start_date <= body.end_date);
    if (body.half_day_period) assert.equal(body.start_date, body.end_date);
  }
});
