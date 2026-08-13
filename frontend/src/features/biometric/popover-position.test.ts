import assert from "node:assert/strict";
import { test } from "node:test";

// Relative .ts import: the host-Node harness resolves no `@/` alias for values.
import {
  ANCHOR_GAP,
  ARROW_INSET,
  computePopoverPosition,
  fitsInViewport,
  SHEET_MAX_WIDTH,
  VIEWPORT_MARGIN,
  type AnchorRect,
  type PopoverMetrics,
} from "./popover-position.ts";

const W = 260; // popover width
const H = 170; // popover height

/** A desktop viewport with a day cell somewhere in the middle of the grid. */
function metrics(anchor: AnchorRect, over: Partial<PopoverMetrics> = {}): PopoverMetrics {
  return {
    anchor,
    popoverWidth: W,
    popoverHeight: H,
    viewportWidth: 1440,
    viewportHeight: 900,
    ...over,
  };
}

const MID_CELL: AnchorRect = { top: 500, left: 600, width: 120, height: 86 };

// ── vertical placement ──────────────────────────────────────────────────────

test("opens above the day when there is room", () => {
  const p = computePopoverPosition(metrics(MID_CELL));
  assert.equal(p.placement, "top");
  // Sits exactly one gap above the cell.
  assert.equal(p.top, MID_CELL.top - ANCHOR_GAP - H);
});

test("flips below when the day is near the top of the viewport", () => {
  const p = computePopoverPosition(metrics({ ...MID_CELL, top: 40 }));
  assert.equal(p.placement, "bottom");
  assert.equal(p.top, 40 + MID_CELL.height + ANCHOR_GAP);
});

test("stays above when the day is near the bottom", () => {
  const p = computePopoverPosition(metrics({ ...MID_CELL, top: 800 }));
  assert.equal(p.placement, "top");
  assert.ok(fitsInViewport(p, metrics(MID_CELL)));
});

test("the exact boundary between above and below", () => {
  // Just enough room above: top === margin + needed.
  const justEnough = VIEWPORT_MARGIN + H + ANCHOR_GAP;
  assert.equal(
    computePopoverPosition(metrics({ ...MID_CELL, top: justEnough })).placement,
    "top",
  );
  assert.equal(
    computePopoverPosition(metrics({ ...MID_CELL, top: justEnough - 1 })).placement,
    "bottom",
  );
});

test("picks the roomier side when neither side fits, and never overflows", () => {
  // A short viewport where the popover fits on neither side of the cell.
  const m = metrics({ top: 100, left: 600, width: 120, height: 86 }, {
    viewportHeight: 260,
  });
  const p = computePopoverPosition(m);
  assert.ok(p.placement === "top" || p.placement === "bottom");
  assert.ok(fitsInViewport(p, m), "clamped into the viewport");
  assert.ok(p.top >= VIEWPORT_MARGIN);
});

// ── horizontal placement ───────────────────────────────────────────────────

test("centres on the day when nothing is in the way", () => {
  const p = computePopoverPosition(metrics(MID_CELL));
  const centre = MID_CELL.left + MID_CELL.width / 2;
  assert.equal(p.left, centre - W / 2);
  // Caret sits dead centre of the popover.
  assert.equal(p.arrowLeft, W / 2);
});

test("clamps at the left edge for the first column", () => {
  const m = metrics({ top: 500, left: 4, width: 120, height: 86 });
  const p = computePopoverPosition(m);
  assert.equal(p.left, VIEWPORT_MARGIN);
  assert.ok(fitsInViewport(p, m));
});

test("clamps at the right edge for the last column", () => {
  const m = metrics({ top: 500, left: 1400, width: 120, height: 86 });
  const p = computePopoverPosition(m);
  assert.equal(p.left, 1440 - W - VIEWPORT_MARGIN);
  assert.ok(fitsInViewport(p, m));
});

test("never overflows across a whole week of cells", () => {
  // Seven adjacent columns, exactly how the calendar grid is laid out.
  for (let col = 0; col < 7; col += 1) {
    const m = metrics({ top: 500, left: 40 + col * 120, width: 120, height: 86 });
    const p = computePopoverPosition(m);
    assert.ok(fitsInViewport(p, m), `column ${col} overflowed`);
  }
});

// ── the caret ──────────────────────────────────────────────────────────────

test("the caret follows the day after the popover is clamped", () => {
  const m = metrics({ top: 500, left: 4, width: 120, height: 86 });
  const p = computePopoverPosition(m);
  const centre = 4 + 60;
  assert.equal(p.arrowLeft, centre - p.left);
  // Still pointing at the cell, not at the popover's middle.
  assert.notEqual(p.arrowLeft, W / 2);
});

test("the caret never sits on a rounded corner", () => {
  for (const left of [0, 2, 20, 1380, 1430, 1439]) {
    const m = metrics({ top: 500, left, width: 120, height: 86 });
    const p = computePopoverPosition(m);
    if (p.arrowLeft === null) continue;
    assert.ok(p.arrowLeft >= ARROW_INSET, `caret too close to the left corner`);
    assert.ok(p.arrowLeft <= W - ARROW_INSET, `caret too close to the right corner`);
  }
});

test("the caret is dropped when the day is not behind the popover at all", () => {
  // A very wide viewport with a cell far outside the clamped popover.
  const m = metrics({ top: 500, left: 3000, width: 120, height: 86 }, {
    viewportWidth: 900,
  });
  const p = computePopoverPosition(m);
  assert.equal(p.arrowLeft, null);
});

// ── mobile fallback ────────────────────────────────────────────────────────

test("narrow viewports fall back to a bottom sheet", () => {
  const p = computePopoverPosition(metrics(MID_CELL, { viewportWidth: 390 }));
  assert.equal(p.placement, "sheet");
  assert.equal(p.arrowLeft, null);
});

test("the sheet breakpoint is inclusive", () => {
  assert.equal(
    computePopoverPosition(metrics(MID_CELL, { viewportWidth: SHEET_MAX_WIDTH }))
      .placement,
    "sheet",
  );
  assert.notEqual(
    computePopoverPosition(metrics(MID_CELL, { viewportWidth: SHEET_MAX_WIDTH + 1 }))
      .placement,
    "sheet",
  );
});

test("a tablet keeps the contextual popover", () => {
  const m = metrics({ top: 400, left: 300, width: 100, height: 86 }, {
    viewportWidth: 834,
    viewportHeight: 1112,
  });
  const p = computePopoverPosition(m);
  assert.notEqual(p.placement, "sheet");
  assert.ok(fitsInViewport(p, m));
});

// ── degenerate input ───────────────────────────────────────────────────────

test("a popover taller than the viewport is clamped, not hidden", () => {
  const m = metrics(MID_CELL, { viewportHeight: 100 });
  const p = computePopoverPosition(m);
  assert.equal(p.top, VIEWPORT_MARGIN);
});

test("a popover wider than the viewport is clamped, not hidden", () => {
  const m = metrics(MID_CELL, { viewportWidth: 600, popoverWidth: 700 });
  const p = computePopoverPosition(m);
  assert.equal(p.left, VIEWPORT_MARGIN);
});

test("fitsInViewport always accepts a sheet", () => {
  assert.equal(
    fitsInViewport(
      { placement: "sheet", top: 0, left: 0, arrowLeft: null },
      { popoverWidth: W, popoverHeight: H, viewportWidth: 390, viewportHeight: 700 },
    ),
    true,
  );
});
