"use client";

import * as React from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/utils";

import {
  buildDayDetail,
  EMPTY_VALUE,
  formatDuration,
  statusLine,
  type BiometricClassification,
  type DaySummaryLike,
} from "../day-detail";
import { formatISTTime } from "../mapping-format";
import {
  computePopoverPosition,
  type AnchorRect,
  type PopoverPosition,
} from "../popover-position";
/**
 * A contextual macOS-style popover for one attendance day.
 *
 * Shared by the calendar (anchored to a day cell) and the PM review screen
 * (anchored to a table row). Both pass the same `DaySummaryLike` shape, so there
 * is one detail panel rather than two that drift apart.
 *
 * NOT a modal and NOT a drawer: no backdrop, no blur, no dimming. The calendar
 * stays fully visible and readable behind it, and a caret points back at the day
 * that opened it. Deliberately not built on `Dialog`, whose whole contract is a
 * full-screen blurred overlay - reusing it here would reintroduce exactly the
 * appearance this is replacing.
 *
 * Placement comes from `popover-position.ts` (pure, unit-tested): above the day
 * when it fits, below when it does not, clamped so it can never leave the
 * viewport, with the caret tracking the day even after clamping. Below 480px it
 * becomes a bottom sheet with identical content.
 *
 * Read-only. Nothing here writes, and nothing here decides: the duration and the
 * classification arrive computed by the backend and are formatted, not derived.
 */
export function AttendanceDayPopover({
  anchor,
  title,
  subtitle,
  summary,
  attendanceLabel,
  reason,
  onClose,
}: {
  /** The element that opened this (a calendar day, or a review row), or null. */
  anchor: HTMLElement | null;
  /** The heading: the date on the calendar, the employee on the review screen. */
  title: string;
  /** Optional second line - the date, when the heading is an employee. */
  subtitle?: string | null;
  /** The row for this day, or undefined when there are no punches. */
  summary: DaySummaryLike | undefined;
  /** The official attendance status label for the day, when a record exists. */
  attendanceLabel: string | null;
  /** The reason a manager recorded for this day. Their words, not a system
   *  slug - shown verbatim so the employee reads exactly what was written. */
  reason?: string | null;
  onClose: () => void;
}) {
  const coreOpsTime = useCoreOpsClock();
  const cardRef = React.useRef<HTMLDivElement>(null);
  const [position, setPosition] = React.useState<PopoverPosition | null>(null);
  const [visible, setVisible] = React.useState(false);

  // Measure, then place. Runs before paint so the card never appears at 0,0 and
  // jump - it stays invisible until a position exists.
  const place = React.useCallback(() => {
    const card = cardRef.current;
    if (!anchor || !card) return;
    const rect = anchor.getBoundingClientRect();
    const box: AnchorRect = {
      top: rect.top,
      left: rect.left,
      width: rect.width,
      height: rect.height,
    };
    setPosition(
      computePopoverPosition({
        anchor: box,
        popoverWidth: card.offsetWidth,
        popoverHeight: card.offsetHeight,
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
      }),
    );
  }, [anchor]);

  React.useLayoutEffect(() => {
    if (!anchor) {
      setPosition(null);
      setVisible(false);
      return;
    }
    place();
    // One frame later, fade in - so the transition runs from the correct spot.
    const id = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(id);
  }, [anchor, place]);

  // Keep it attached while the page moves underneath.
  React.useEffect(() => {
    if (!anchor) return;
    window.addEventListener("resize", place);
    // Capture phase: catches scrolling of the page AND any scroll container.
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [anchor, place]);

  // Escape closes, and focus returns to the day that opened it.
  React.useEffect(() => {
    if (!anchor) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [anchor, onClose]);

  // Click anywhere outside closes. The anchor itself is excluded so the calendar
  // handles a second click on the same day as a toggle rather than a double event.
  React.useEffect(() => {
    if (!anchor) return;
    function onPointerDown(e: MouseEvent) {
      const target = e.target as Node;
      if (cardRef.current?.contains(target)) return;
      if (anchor?.contains(target)) return;
      onClose();
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [anchor, onClose]);

  if (!anchor || typeof document === "undefined") return null;

  const detail = buildDayDetail(summary);
  const sheet = position?.placement === "sheet";

  return createPortal(
    <div
      ref={cardRef}
      role="dialog"
      aria-label={`Attendance for ${subtitle ? `${title}, ${subtitle}` : title}`}
      style={
        sheet
          ? undefined
          : { top: position?.top ?? 0, left: position?.left ?? 0, width: CARD_WIDTH }
      }
      className={cn(
        "z-50 rounded-lg border border-border bg-card shadow-lg",
        // Subtle fade + lift. Instant-feeling, and disabled outright for anyone
        // who asked for reduced motion.
        "transition-[opacity,transform] duration-150 ease-out",
        "motion-reduce:transition-none",
        sheet
          ? "fixed inset-x-2 bottom-2 rounded-xl"
          : "fixed origin-bottom",
        visible && position
          ? "opacity-100 translate-y-0 scale-100"
          : "pointer-events-none opacity-0 scale-[0.98] motion-reduce:scale-100",
        !visible && !sheet && "translate-y-1 motion-reduce:translate-y-0",
      )}
    >
      {/* The caret. Rotated square straddling the border, so only two of its
          edges show and it reads as a continuation of the card. */}
      {!sheet && position?.arrowLeft != null && (
        <span
          aria-hidden
          style={{
            left: position.arrowLeft,
            ...(position.placement === "top" ? { bottom: -5 } : { top: -5 }),
          }}
          className={cn(
            "pointer-events-none absolute h-2.5 w-2.5 -translate-x-1/2 rotate-45 bg-card",
            position.placement === "top"
              ? "border-b border-r border-border"
              : "border-l border-t border-border",
          )}
        />
      )}

      <div className="p-3.5">
        <p className="font-serif text-sm font-semibold leading-tight">{title}</p>
        {subtitle && (
          <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>
        )}

        <div className="mt-3">
          <Micro>CoreOps time</Micro>
          {/* The live company clock, not the contracted window - the scheduled
              length already has its own field below, and repeating it here said
              the same thing twice. */}
          <p className="tabular mt-0.5 text-base font-bold">{coreOpsTime}</p>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-3 border-t border-border pt-3">
          <div>
            <Micro>First IN</Micro>
            <p className="tabular mt-0.5 text-base font-semibold">
              {detail.firstIn ? formatISTTime(detail.firstIn) : EMPTY_VALUE}
            </p>
          </div>
          <div>
            <Micro>Last OUT</Micro>
            <p
              className={cn(
                "tabular mt-0.5 text-base font-semibold",
                !detail.lastOut && "text-muted-foreground",
              )}
            >
              {detail.lastOut ? formatISTTime(detail.lastOut) : EMPTY_VALUE}
            </p>
          </div>
          <div>
            <Micro>Worked</Micro>
            {/* Straight from the API. A missing OUT shows "-", never the
                scheduled end standing in for a punch nobody made. */}
            <p
              className={cn(
                "tabular mt-0.5 text-sm font-semibold",
                detail.workedMinutes == null && "text-muted-foreground",
              )}
            >
              {formatDuration(detail.workedMinutes)}
            </p>
          </div>
          <div>
            <Micro>Scheduled</Micro>
            <p className="tabular mt-0.5 text-sm font-semibold text-muted-foreground">
              {formatDuration(detail.scheduledMinutes)}
            </p>
          </div>
          {/* NO Permission field here, deliberately. The status line below
              already reads "Present | 1hr · 6h 35m", and a separate Permission
              row said the same thing twice in a 232px card. The four values in
              this grid are the ones the permission does NOT change. */}
        </div>

        <div className="mt-3 flex items-center gap-2 border-t border-border pt-3">
          <span
            aria-hidden
            className={cn("h-1.5 w-1.5 shrink-0 rounded-full", DOT[detail.classification])}
          />
          <p className="text-xs font-medium">
            {statusLine(detail, attendanceLabel)}
          </p>
        </div>

        {/* The manager's own words for why this day reads the way it does. Only
            shown when somebody actually wrote one - an unexplained day says
            nothing rather than showing an empty heading. */}
        {reason && (
          <div className="mt-3 border-t border-border pt-3">
            <Micro>Reason</Micro>
            <p className="mt-0.5 whitespace-pre-line text-xs leading-snug">
              {reason}
            </p>
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}

/**
 * The current company wall clock, `HH:MM:SS` in Asia/Kolkata, ticking.
 *
 * Pinned to the office timezone rather than the viewer's, so a PM working from
 * anywhere reads the same clock the office does. Seconds tick once a second -
 * the point is that it visibly moves, which is what makes it read as a live
 * clock rather than a static field. The interval is cleared on unmount, and the
 * popover is short-lived, so this is a handful of renders.
 *
 * Rendered only after mount: the server and the browser are never in the same
 * second, so painting a clock during SSR would guarantee a hydration mismatch.
 * Until then it shows a dash rather than a wrong time.
 */
function useCoreOpsClock(): string {
  const [now, setNow] = React.useState<string | null>(null);

  React.useEffect(() => {
    const read = () =>
      setNow(
        // Read on the 24-hour clock (stable across engines), rendered on the
        // 12-hour one CoreOps uses everywhere. `en-GB`'s own 12-hour output
        // varies by ICU version in case and padding, which a ticking clock
        // would show off once a second.
        (() => {
          const [hh, mm, ss] = new Date()
            .toLocaleTimeString("en-GB", {
              timeZone: "Asia/Kolkata",
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
              hour12: false,
            })
            .split(":");
          const hour = Number(hh) % 24;
          const period = hour < 12 ? "AM" : "PM";
          const h12 = hour % 12 === 0 ? 12 : hour % 12;
          return `${String(h12).padStart(2, "0")}:${mm}:${ss} ${period}`;
        })(),
      );
    read();
    const id = window.setInterval(read, 1000);
    return () => window.clearInterval(id);
  }, []);

  return now ?? EMPTY_VALUE;
}

/** Compact by design: this sits next to a day cell, not in a page column. */
const CARD_WIDTH = 232;

/** Matches the calendar legend's dot vocabulary, so a colour means one thing.
 *  `needs_review` shares amber with `incomplete`: both mean "a human still has to
 *  look at this", and splitting them by colour would suggest one is settled. */
const DOT: Record<BiometricClassification, string> = {
  present: "bg-emerald-500",
  incomplete: "bg-amber-500",
  needs_review: "bg-amber-500",
  no_record: "bg-slate-300",
};

function Micro({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
      {children}
    </span>
  );
}
