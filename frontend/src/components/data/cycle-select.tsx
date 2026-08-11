"use client";

import * as React from "react";
import { CalendarDays, Check, ChevronDown } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { weekStartISO } from "@/features/dashboard/utils";

/**
 * The Friday-Thursday cycle selector.
 *
 * One control, shared by every surface that is scoped to a benchmark cycle -
 * Employee Performance on the PM dashboard and the project Weekly Report. It
 * was extracted from the first of those rather than reimplemented for the
 * second: two visually similar week pickers would inevitably drift apart in
 * wording, date format and behaviour, and the user has to recognise them as the
 * same thing.
 *
 * Surfaces differ only in HOW MANY cycles they offer (`options`) and what each
 * one is called (`labels`), because that is a backend fact - Employee
 * Performance accepts four weeks back, the Weekly Report accepts two. Nothing
 * about the presentation is configurable.
 */

const MONTHS_SHORT = [
  "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
  "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
];

/**
 * Compact date range for a cycle - Friday to Thursday, anchored to IST via
 * `weekStartISO()`, `weekOffset` whole weeks back from the current cycle.
 * Computed from the same one-line rule as the backend
 * (start = currentStart - 7 * offset, end = start + 6), so the label always
 * names the window the API will actually return.
 *
 * Handles a cycle that spans two months ("JUN 26 – JUL 2").
 *
 * The dash characters below are the ones Employee Performance already ships;
 * they are kept verbatim so the two selectors are pixel-identical.
 */
export function cycleRangeLabel(weekOffset: number): string {
  const [y, m, d] = weekStartISO().split("-").map(Number);
  const fri = new Date(y, m - 1, d - 7 * weekOffset);
  const thu = new Date(y, m - 1, d - 7 * weekOffset + 6);
  if (fri.getMonth() === thu.getMonth()) {
    return `${MONTHS_SHORT[fri.getMonth()]} ${fri.getDate()}–${thu.getDate()}`;
  }
  return `${MONTHS_SHORT[fri.getMonth()]} ${fri.getDate()} – ${MONTHS_SHORT[thu.getMonth()]} ${thu.getDate()}`;
}

export interface CycleSelectProps {
  /** Selected whole-week offset back from the cycle containing today. */
  value: number;
  /** Offsets to offer, in menu order (nearest first). */
  options: readonly number[];
  /** Display name per offset, e.g. { 0: "Current week", 1: "Previous week" }. */
  labels: Record<number, string>;
  onChange: (weekOffset: number) => void;
  /** Names the control for screen readers; the trigger has no visible label. */
  ariaLabel: string;
}

export function CycleSelect({
  value,
  options,
  labels,
  onChange,
  ariaLabel,
}: CycleSelectProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={ariaLabel}
          className="inline-flex h-9 items-center gap-2 rounded-md border border-input bg-card px-3 text-sm shadow-sm transition-colors hover:bg-secondary"
        >
          <CalendarDays className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="text-muted-foreground">{labels[value]}</span>
          {/* The dates live inside the trigger, never on a second line: the
              selected cycle and the days it covers are one fact. */}
          <span className="font-semibold tabular text-foreground">
            {cycleRangeLabel(value)}
          </span>
          <span className="text-xs text-muted-foreground">Fri–Thu</span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {options.map((option) => (
          <DropdownMenuItem key={option} onSelect={() => onChange(option)}>
            <div className="flex-1">
              <div className="font-medium">{labels[option]}</div>
              <div className="text-xs text-muted-foreground">
                {cycleRangeLabel(option)} · Fri–Thu
              </div>
            </div>
            {value === option && (
              <Check className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
            )}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
