/**
 * Contextual popover placement. Pure geometry - no DOM, no React.
 *
 * No imports, no `@/` alias: the host-Node unit test loads this file directly.
 * Everything is arithmetic on plain rectangles, so the rules that matter (never
 * clip the viewport, keep the caret pointing at the anchor) are testable without
 * a browser.
 *
 * The caller measures the anchor and the popover with getBoundingClientRect and
 * passes viewport-relative numbers; the result is meant for `position: fixed`.
 */

/** Distance between the anchor edge and the popover edge - room for the caret. */
export const ANCHOR_GAP = 10;
/** Smallest allowed distance from any viewport edge. */
export const VIEWPORT_MARGIN = 12;
/** How far the caret centre must stay from the popover's own corners, so it can
 *  never sit on the rounded corner radius. */
export const ARROW_INSET = 18;
/** Below this width a contextual popover cannot sit comfortably beside a day
 *  cell, so the caller switches to a bottom sheet. */
export const SHEET_MAX_WIDTH = 480;

export interface AnchorRect {
  top: number;
  left: number;
  width: number;
  height: number;
}

/** `top`/`bottom` are relative to the anchor; `sheet` ignores the anchor. */
export type PopoverPlacement = "top" | "bottom" | "sheet";

export interface PopoverPosition {
  placement: PopoverPlacement;
  /** Viewport-relative, for `position: fixed`. Both 0 when placement is sheet. */
  top: number;
  left: number;
  /** Caret centre, measured from the popover's own left edge. Null when there is
   *  no caret (sheet), or when clamping pushed the popover away from the anchor
   *  far enough that a caret would point at nothing. */
  arrowLeft: number | null;
}

export interface PopoverMetrics {
  anchor: AnchorRect;
  popoverWidth: number;
  popoverHeight: number;
  viewportWidth: number;
  viewportHeight: number;
  gap?: number;
  margin?: number;
}

function clamp(value: number, min: number, max: number): number {
  // max < min happens when the popover is larger than the space available; the
  // lower bound wins so the popover stays reachable rather than flying off.
  if (max < min) return min;
  return Math.min(Math.max(value, min), max);
}

/**
 * Where to put the popover for a given anchor.
 *
 * Vertical: above the anchor when it fits, otherwise below; when neither side
 * fits, the roomier side wins and the result is clamped into the viewport.
 * Horizontal: centred on the anchor, then clamped so neither edge escapes.
 *
 * Above is preferred because a calendar is read top-to-bottom - opening upward
 * covers days the user has already looked at rather than the ones below.
 */
export function computePopoverPosition({
  anchor,
  popoverWidth,
  popoverHeight,
  viewportWidth,
  viewportHeight,
  gap = ANCHOR_GAP,
  margin = VIEWPORT_MARGIN,
}: PopoverMetrics): PopoverPosition {
  if (viewportWidth <= SHEET_MAX_WIDTH) {
    return { placement: "sheet", top: 0, left: 0, arrowLeft: null };
  }

  const spaceAbove = anchor.top - margin;
  const spaceBelow = viewportHeight - (anchor.top + anchor.height) - margin;
  const needed = popoverHeight + gap;

  let placement: "top" | "bottom";
  if (spaceAbove >= needed) placement = "top";
  else if (spaceBelow >= needed) placement = "bottom";
  else placement = spaceAbove >= spaceBelow ? "top" : "bottom";

  const rawTop =
    placement === "top"
      ? anchor.top - gap - popoverHeight
      : anchor.top + anchor.height + gap;
  const top = clamp(rawTop, margin, viewportHeight - popoverHeight - margin);

  const anchorCentre = anchor.left + anchor.width / 2;
  const left = clamp(
    anchorCentre - popoverWidth / 2,
    margin,
    viewportWidth - popoverWidth - margin,
  );

  // The caret tracks the anchor even after the popover was clamped sideways,
  // which is what keeps a day at the very edge of the grid visually connected.
  const rawArrow = anchorCentre - left;
  const arrowLeft =
    rawArrow < 0 || rawArrow > popoverWidth
      ? null // anchor is not behind the popover at all - drop the caret
      : clamp(rawArrow, ARROW_INSET, popoverWidth - ARROW_INSET);

  return { placement, top, left, arrowLeft };
}

/** True when the popover, at this position, sits fully inside the viewport. */
export function fitsInViewport(
  position: PopoverPosition,
  metrics: Pick<
    PopoverMetrics,
    "popoverWidth" | "popoverHeight" | "viewportWidth" | "viewportHeight"
  >,
): boolean {
  if (position.placement === "sheet") return true;
  return (
    position.top >= 0 &&
    position.left >= 0 &&
    position.top + metrics.popoverHeight <= metrics.viewportHeight &&
    position.left + metrics.popoverWidth <= metrics.viewportWidth
  );
}
