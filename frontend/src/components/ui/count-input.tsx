"use client";

import * as React from "react";

import { Input } from "@/components/ui/input";
import { isCountString } from "@/lib/count-string";

/**
 * Non-negative whole-number input for count fields (tags / docs / BOM /
 * spares / pages / records and any future count).
 *
 * Deliberately NOT `type="number"`: a focused native number input increments
 * or decrements when the page is scrolled with the mouse wheel — exactly what
 * happens when a user types a count and then scrolls down to reach Save — and
 * it also accepts "e", "E", "+", "-" and ".". `type="text"` +
 * `inputMode="numeric"` + `pattern="[0-9]*"` keeps the mobile numeric
 * keyboard while having no spinners and no wheel behaviour at all.
 *
 * The form value stays a string. Only an empty string or ASCII digits are let
 * through (see isCountString); any other change is dropped, and the
 * controlled input reverts it. Nothing is converted or clamped while typing —
 * schema validation and the API-body converter (schemas.ts `toCount`) remain
 * the only authorities.
 */
export type CountInputProps = Omit<
  React.InputHTMLAttributes<HTMLInputElement>,
  "type" | "inputMode" | "pattern"
>;

const CountInput = React.forwardRef<HTMLInputElement, CountInputProps>(
  ({ onChange, ...props }, ref) => (
    <Input
      {...props}
      ref={ref}
      type="text"
      inputMode="numeric"
      pattern="[0-9]*"
      autoComplete="off"
      onChange={(event) => {
        if (isCountString(event.target.value)) onChange?.(event);
      }}
    />
  ),
);
CountInput.displayName = "CountInput";

export { CountInput };
