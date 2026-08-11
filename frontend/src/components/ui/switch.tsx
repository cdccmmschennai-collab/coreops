"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

export interface SwitchProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  id?: string;
  /** Accessible name when no visible <label> is wired to `id`. */
  "aria-label"?: string;
  className?: string;
}

/**
 * On/off toggle for a single boolean setting.
 *
 * A real <button role="switch"> rather than a styled checkbox: it carries
 * aria-checked natively, so screen readers announce "on"/"off" instead of
 * "checked", and it takes keyboard Space/Enter for free. No Radix dependency —
 * same call as `checkbox.tsx`, since this is the only switch in the app.
 *
 * Deliberately controlled-only: a project's scope is loaded from the record and
 * submitted with the form, so an internal uncontrolled state would just be a
 * second source of truth to keep in step.
 */
const Switch = React.forwardRef<HTMLButtonElement, SwitchProps>(
  ({ checked, onCheckedChange, disabled, className, ...props }, ref) => (
    <button
      ref={ref}
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "bg-primary" : "bg-input",
        className,
      )}
      {...props}
    >
      <span
        aria-hidden
        className={cn(
          "pointer-events-none block h-4 w-4 rounded-full bg-background shadow-sm ring-0 transition-transform",
          checked ? "translate-x-4" : "translate-x-0",
        )}
      />
    </button>
  ),
);
Switch.displayName = "Switch";

export { Switch };
